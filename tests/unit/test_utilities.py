from __future__ import annotations

import asyncio
import gc
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import pytest
from pydantic import BaseModel

from patera.response import Response
from patera.utilities import (
    _extract_response_type,
    base64_to_bytes,
    development,
    find_python_files_by_name,
    fs_safe_join,
    ignore,
    pascal_to_upper_snake,
    run_in_background,
    run_sync_or_async,
    to_kebab_case,
)

if TYPE_CHECKING:
    from some_module_that_does_not_exist import Missing  # noqa: F401


class Item(BaseModel):
    name: str


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("PascalCase", "PASCAL_CASE"),
        ("HTTPServer", "HTTP_SERVER"),
        ("MyXMLParser", "MY_XML_PARSER"),
        ("SqlDatabaseManager", "SQL_DATABASE_MANAGER"),
        ("", ""),
    ],
)
def test_pascal_to_upper_snake(name, expected):
    assert pascal_to_upper_snake(name) == expected


def test_to_kebab_case():
    assert to_kebab_case("Hello World_again!") == "hello-world-again"


def test_base64_to_bytes_supports_data_urls():
    assert base64_to_bytes("aGVsbG8=") == b"hello"
    assert base64_to_bytes("data:text/plain;base64,aGVsbG8=") == b"hello"


def test_fs_safe_join_blocks_traversal(tmp_path: Path):
    (tmp_path / "a.txt").write_text("x")
    assert fs_safe_join(tmp_path, "a.txt") == (tmp_path / "a.txt").resolve()
    with pytest.raises(FileNotFoundError):
        fs_safe_join(tmp_path, "..", "etc", "passwd")


def test_find_python_files_by_name(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "users_api.py").write_text("")
    (tmp_path / "sub" / "orders_controller.py").write_text("")
    (tmp_path / "helpers.py").write_text("")
    found = {p.name for p in find_python_files_by_name(tmp_path, ["api", "controller"])}
    assert found == {"users_api.py", "orders_controller.py"}
    assert find_python_files_by_name(tmp_path / "missing", ["api"]) == []


def test_development_and_ignore_markers():
    @development
    class A: ...

    @ignore
    class B: ...

    assert A._development is True
    assert B._ignore is True


async def test_run_sync_or_async_handles_both():
    async def coro(x):
        return x * 2

    def sync(x):
        return x + 1

    assert await run_sync_or_async(coro, 2) == 4
    assert await run_sync_or_async(sync, 2) == 3


async def test_run_in_background_keeps_task_alive_and_logs_errors(caplog):
    done = asyncio.Event()

    async def job():
        await asyncio.sleep(0.01)
        done.set()

    run_in_background(job)
    gc.collect()  # the task must not be garbage collected
    await asyncio.wait_for(done.wait(), 1)

    async def failing():
        raise RuntimeError("boom")

    task = run_in_background(failing)
    with pytest.raises(RuntimeError):
        await task


class TestExtractResponseType:
    def test_plain_response(self):
        def handler() -> Response:  # type: ignore[empty-body]
            ...

        assert _extract_response_type(handler) is None

    def test_parametrized_response(self):
        def handler() -> Response[Item]:  # type: ignore[empty-body]
            ...

        assert _extract_response_type(handler) is Item

    def test_annotated_response(self):
        def handler() -> Response[Annotated[Item, "meta"]]:  # type: ignore[empty-body]
            ...

        assert _extract_response_type(handler) is Item

    def test_unresolvable_annotation_does_not_raise(self):
        def handler() -> "Missing":  # type: ignore[name-defined]  # noqa: F821
            ...

        assert _extract_response_type(handler) is None

    def test_bound_methods_are_supported(self):
        class Ctrl:
            def handler(self) -> Response[Item]:  # type: ignore[empty-body]
                ...

        assert _extract_response_type(Ctrl().handler) is Item


class _AsyncCallable:
    async def __call__(self, value):
        await asyncio.sleep(0)
        return value * 10


async def test_run_sync_or_async_detects_async_callables():
    import functools
    import threading

    main_thread = threading.get_ident()

    async def coro(a, b):
        return (a + b, threading.get_ident())

    assert await run_sync_or_async(_AsyncCallable(), 2) == 20
    result, thread = await run_sync_or_async(functools.partial(coro, 1), 2)
    assert result == 3 and thread == main_thread
    # A sync callable returning a coroutine has it awaited
    assert await run_sync_or_async(lambda: coro(2, 2)) == (4, main_thread)


async def test_background_tasks_finish_or_are_cancelled():
    from patera.utilities import wait_for_background_tasks

    finished = []

    async def quick():
        await asyncio.sleep(0.01)
        finished.append("quick")

    async def slow():
        await asyncio.sleep(30)
        finished.append("slow")

    run_in_background(quick)
    slow_task = run_in_background(slow)
    assert await wait_for_background_tasks(timeout=0.2) == (1, 1)
    assert finished == ["quick"]
    assert slow_task.cancelled()
    assert await wait_for_background_tasks(timeout=0.2) == (0, 0)
