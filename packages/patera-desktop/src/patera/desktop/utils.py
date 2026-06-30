import asyncio
import threading
from functools import wraps
from typing import Any, Callable
from collections.abc import Coroutine

from patera.utilities import run_sync_or_async


def _underlying_function(value: Any) -> Any:
    """
    Return the original function for bound methods.

    For instance methods:
        api.my_func        -> bound method
        api.my_func.__func__ -> original function object

    The decorator metadata is stored on the original function object.
    """
    return getattr(value, "__func__", value)


def is_frontend_tool(value: Any) -> bool:
    original = _underlying_function(value)

    return bool(
        getattr(value, "_frontend_tool", False)
        or getattr(original, "_frontend_tool", False)
    )


def get_frontend_tool_name(value: Callable[..., Any]) -> str:
    original = _underlying_function(value)

    return (
        getattr(value, "_frontend_tool_name", None)
        or getattr(original, "_frontend_tool_name", None)
        or value.__name__
    )


def run_coroutine_blocking(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run a coroutine from synchronous code.

    pywebview expects exposed Python functions to be normal callables.
    This helper lets the normal callable internally execute async code.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_container: dict[str, Any] = {}
    error_container: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result_container["result"] = asyncio.run(coro)
        except BaseException as exc:
            error_container["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in error_container:
        raise error_container["error"]

    return result_container.get("result")


def make_exposed_frontend_tool(method: Callable[..., Any]) -> Callable[..., Any]:
    frontend_name = get_frontend_tool_name(method)

    @wraps(method)
    def exposed(*args: Any, **kwargs: Any) -> Any:
        return run_coroutine_blocking(run_sync_or_async(method, *args, **kwargs))

    exposed.__name__ = frontend_name
    return exposed
