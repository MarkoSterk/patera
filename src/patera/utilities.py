"""
Utility methods for Patera
"""

from __future__ import annotations
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    List,
    Optional,
    Type,
    get_origin,
    get_type_hints,
    get_args,
    Annotated,
    TYPE_CHECKING,
)
import asyncio
import functools
import importlib
import importlib.util
import inspect
import mimetypes
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote
from base64 import b64decode
from email.utils import formatdate, parsedate_to_datetime
from asyncio import Task


from .http_statuses import HttpStatus

if TYPE_CHECKING:
    from .response import Response


def to_kebab_case(text: str) -> str:
    """Convert a string into lower-kebab-case."""
    # replace non-alphanumeric with spaces, trim, replace whitespace with dash
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip()
    return re.sub(r"\s+", "-", text).lower()


def pascal_to_upper_snake(name: str) -> str:
    """
    Convert PascalCase (or CamelCase) to UPPER_SNAKE_CASE.
    Examples:
        PascalCase -> PASCAL_CASE
        HTTPServer -> HTTP_SERVER
        MyXMLParser -> MY_XML_PARSER
    """
    if not name:
        return name
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)

    return s2.upper()


_RESPONSE_TYPE_CACHE: dict[Any, Optional[Type[Any]]] = {}


def _extract_response_type(func) -> Optional[Type[Any]]:
    """
    If the function is annotated as -> Response[T], return T; else None.

    Results are cached per function. Annotations that cannot be resolved at
    runtime (e.g. names imported only under TYPE_CHECKING) yield None instead
    of failing the request.
    """
    target = getattr(func, "__func__", func)
    try:
        return _RESPONSE_TYPE_CACHE[target]
    except (KeyError, TypeError):
        pass

    result = _compute_response_type(target)

    try:
        _RESPONSE_TYPE_CACHE[target] = result
    except TypeError:  # pragma: no cover - unhashable callable
        pass
    return result


def _compute_response_type(func) -> Optional[Type[Any]]:
    from .response import Response  # avoid circular import

    try:
        hints = get_type_hints(func, include_extras=True)
    except Exception:
        return None
    ret = hints.get("return")
    if ret is None:
        return None
    if get_origin(ret) is Response:
        args = get_args(ret)
        if args:
            t = args[0]
            if get_origin(t) is Annotated:  # peel Annotated[T, ...]
                t = get_args(t)[0]
            return t
    return None


def import_module(import_string: str):
    """Imports ``module:attribute`` and returns the attribute."""
    module_path, obj_name = import_string.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, obj_name)


def get_app_root_path(import_name: str) -> str:
    """
    Finds the root path of the application package on the file system or
    uses the current working directory
    """
    # First, check if the module is already imported and has a __file__ attribute.
    mod = sys.modules.get(import_name)
    if mod is not None and hasattr(mod, "__file__"):
        return os.path.dirname(os.path.abspath(mod.__file__))  # type: ignore

    # Tries to load the modules loader
    loader = importlib.util.find_spec(import_name)
    if loader is None or import_name == "__main__":
        return os.getcwd()

    # Checks if loader has a filename
    filepath = None
    if hasattr(loader, "get_filename"):
        filepath = loader.get_filename(import_name)  # type: ignore

    # Tries to lookup the loaders path attribute
    if not filepath and hasattr(loader, "path"):
        filepath = loader.path  # type: ignore

    if filepath is None:
        # Current working directory fallback
        return os.getcwd()

    # Return the directory name of the absolute path where the module resides.
    return os.path.dirname(os.path.abspath(filepath))


def is_async_callable(func: Any) -> bool:
    """
    True for coroutine functions, including functools.partial objects
    wrapping one and objects whose __call__ is a coroutine function.
    """
    while isinstance(func, functools.partial):
        func = func.func
    return inspect.iscoroutinefunction(func) or inspect.iscoroutinefunction(
        getattr(func, "__call__", None)
    )


async def run_sync_or_async(func: Callable, *args, **kwargs):
    """
    Runs an async callable directly and a sync callable in a worker thread.
    A sync callable that returns an awaitable (a lambda returning a
    coroutine, for example) has that awaitable awaited too.
    """
    if is_async_callable(func):
        return await func(*args, **kwargs)

    result = await asyncio.to_thread(func, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def run_in_background(func: Callable[..., Any], *args, **kwargs) -> Task:
    """
    Fire-and-forget a function (async or sync) without awaiting its result.

    Important:
    - Detached background tasks should not rely on request-scoped context.
    - Pass only the data the task needs.
    - If database access is needed, open a fresh session inside the task.
    """

    task = asyncio.create_task(run_sync_or_async(func, *args, **kwargs))
    # Keep a strong reference: the event loop only keeps weak references to
    # tasks, so an unreferenced task may be garbage collected mid-execution.
    _BACKGROUND_TASKS.add(task)

    def _handle_task_result(t: asyncio.Task) -> None:
        _BACKGROUND_TASKS.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            from loguru import logger

            logger.opt(exception=exc).error(f"Background task failed: {exc}")

    task.add_done_callback(_handle_task_result)
    return task


_BACKGROUND_TASKS: set[Task] = set()


async def wait_for_background_tasks(timeout: Optional[float]) -> tuple[int, int]:
    """
    Waits for the background tasks started with run_in_background() on the
    running event loop. Tasks still running after ``timeout`` seconds are
    cancelled (None waits without a limit).

    Returns (finished, cancelled) counts. Called by the application on
    shutdown, before its shutdown methods close databases and clients.
    """
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    pending = {
        task
        for task in _BACKGROUND_TASKS
        if task.get_loop() is loop and not task.done() and task is not current
    }
    if not pending:
        return 0, 0
    done, still_running = await asyncio.wait(pending, timeout=timeout)
    for task in still_running:
        task.cancel()
    if still_running:
        await asyncio.gather(*still_running, return_exceptions=True)
    return len(done), len(still_running)


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """
    A Content-Disposition header value for a file name in any language
    (RFC 6266): a plain ``filename`` that every client understands, with
    characters outside ASCII and quotes replaced, and ``filename*`` with the
    exact UTF-8 name, which current browsers prefer.

        content_disposition("poročilo.pdf")
        # 'attachment; filename="poro_ilo.pdf"; filename*=UTF-8\'\'poro%C4%8Dilo.pdf'
    """
    if disposition not in ("attachment", "inline"):
        raise ValueError("disposition must be 'attachment' or 'inline'")
    name = os.path.basename(filename.replace("\\", "/")) or "download"
    fallback = "".join(
        ch if " " <= ch <= "~" and ch not in '"\\' else "_" for ch in name
    )
    value = f'{disposition}; filename="{fallback}"'
    if fallback != name:
        value += f"; filename*=UTF-8''{quote(name, safe='')}"
    return value


def _file_etag(stat: os.stat_result) -> str:
    """Strong ETag for the whole file, from its modification time and size."""
    return f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'


def _etag_matches(header: str, etag: str) -> bool:
    """True if an If-None-Match / If-Range header names this ETag (or "*")."""
    candidates = [part.strip() for part in header.split(",")]
    return "*" in candidates or any(
        candidate.removeprefix("W/") == etag for candidate in candidates
    )


def _parse_http_date(value: str) -> Optional[float]:
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, IndexError):
        return None


def file_response(
    res,
    file_path: str,
    request_headers: Mapping[str, str],
    content_type: Optional[str] = None,
    *,
    cache_control: str = "public, max-age=300",
    download_name: Optional[str] = None,
):
    """
    Prepares a response that streams a file from disk.

    With ``download_name``, browsers save the file under that name instead of
    showing it (``Content-Disposition: attachment``); any language works,
    see content_disposition().

    The same rules apply to every file response:

    - ``ETag`` (from the file's modification time and size), ``Last-Modified``,
      ``Accept-Ranges`` and ``Cache-Control`` are always sent.
    - ``If-None-Match`` / ``If-Modified-Since`` answer 304 Not Modified.
    - A ``Range`` header gives 206 Partial Content (or 416 when it cannot be
      satisfied), unless ``If-Range`` names an older version of the file, in
      which case the whole file is sent.
    - The body is never read into memory: the response records the file, the
      start and the length, and the application streams it while sending.
    """
    stat = os.stat(file_path)
    total = stat.st_size
    etag = _file_etag(stat)
    if content_type is None:
        guessed, _ = mimetypes.guess_type(file_path)
        content_type = guessed or "application/octet-stream"

    headers = {
        "Content-Type": content_type,
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Last-Modified": formatdate(stat.st_mtime, usegmt=True),
        "Cache-Control": cache_control,
    }
    if download_name is not None:
        headers["Content-Disposition"] = content_disposition(download_name)

    if_none_match = request_headers.get("if-none-match")
    if_modified_since = request_headers.get("if-modified-since")
    not_modified = (
        _etag_matches(if_none_match, etag)
        if if_none_match is not None
        else (
            if_modified_since is not None
            and (since := _parse_http_date(if_modified_since)) is not None
            and int(stat.st_mtime) <= since
        )
    )
    if not_modified:
        headers.pop("Content-Type")
        res.status(HttpStatus.NOT_MODIFIED)
        res.set_headers(headers)
        return res

    range_header = request_headers.get("range")
    if_range = request_headers.get("if-range")
    if range_header and if_range:
        if if_range.strip().startswith(('"', "W/")):
            fresh = if_range.strip() == etag
        else:
            since = _parse_http_date(if_range)
            fresh = since is not None and int(stat.st_mtime) <= since
        if not fresh:
            range_header = None

    start, end, status = 0, total - 1, 200
    if range_header:
        m = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", range_header)
        if m and (m.group(1) or m.group(2)):
            if not m.group(1):
                # Suffix range: "bytes=-500" -> the last 500 bytes.
                start, end = max(total - int(m.group(2)), 0), total - 1
            else:
                start = int(m.group(1))
                end = min(int(m.group(2)), total - 1) if m.group(2) else total - 1
            status = 206
            if start >= total or start > end:
                res.status(416)
                res.set_headers(
                    {
                        "Content-Range": f"bytes */{total}",
                        "Accept-Ranges": "bytes",
                        "ETag": etag,
                    }
                )
                return res
        # A missing or unsupported (e.g. multi-range) header sends the file.

    length = max(end - start + 1, 0)
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"

    res.status(status)
    # set_headers normalizes header names (and syncs the media type)
    res.set_headers(headers)
    res.set_zero_copy({"file_path": file_path, "start": start, "length": length})
    return res


def base64_to_bytes(b64_string: str) -> bytes:
    """Turns base64 string to bytes"""
    data: str = (
        b64_string.split(",", 1)[1] if b64_string.startswith("data:") else b64_string
    )
    return b64decode(data)


def fs_safe_join(base: Path, *paths: str) -> Path:
    base = base.resolve()
    candidate = (base / Path(*paths)).resolve()

    try:
        candidate.relative_to(base)
    except ValueError:
        raise FileNotFoundError("Path traversal detected")

    return candidate


def find_python_files_by_name(root_path: Path, keywords: Iterable[str]) -> List[Path]:
    """
    Recursively scans the given root path for Python files whose filenames
    contain ANY of the provided keywords (case-insensitive).

    :param root_path: The root directory to scan
    :param keywords: Iterable of strings to match in filenames
    :return: List of Path objects matching the criteria
    """

    return [
        path
        for path in root_path.rglob("*.py")
        if any(k in path.name.lower() for k in keywords)
    ]


def development(func_or_cls: Callable | Type[Any]) -> Callable | Type[Any]:
    """
    Decorator to mark a controller/cli controller/middleware/logger or endpoint method as development only.
    The decorated class or endpoint will be ignored and unreachable if the
    application is not in DEBUG=True mode.
    """
    setattr(func_or_cls, "_development", True)
    return func_or_cls


def ignore(func_or_cls: Callable | Type[Any]) -> Callable | Type[Any]:
    """
    Decorator to mark a controller/cli controller/middleware/logger as ignored.
    The decorated class will be ignored during startup and runtime.
    """
    setattr(func_or_cls, "_ignore", True)
    return func_or_cls


def encode_response_headers(res: "Response[Any]") -> list[tuple[bytes, bytes]]:
    encoded: list[tuple[bytes, bytes]] = []

    for key, value in res.headers.items():
        encoded.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    for cookie in res.cookies:
        encoded.append((b"set-cookie", cookie.encode("latin-1")))

    return encoded
