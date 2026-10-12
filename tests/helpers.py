"""
Helpers for building throw-away Patera applications in tests.

Every application lives in its own temporary, importable package so that
template/static paths and controller auto-discovery behave exactly like in a
real project.
"""

from __future__ import annotations

import importlib
import itertools
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterable, Optional

from patera import BaseConfig, Patera, app as app_decorator

_counter = itertools.count()

QUIET_LOGGER: dict[str, Any] = {
    "SINK": "STDERR",
    "LEVEL": "ERROR",
    "ENQUEUE": False,
    "COLORIZE": False,
}

# Synchronous writes, so a test can read a record right after logging it.
SYNC_LOG_FILES: dict[str, Any] = {"ENQUEUE": False}


class AppFactory:
    """Creates Patera applications inside temporary packages."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.apps: list[Patera[Any]] = []
        self.packages: list[str] = []
        if str(tmp_path) not in sys.path:
            sys.path.insert(0, str(tmp_path))

    def package(self, files: Optional[dict[str, str]] = None) -> tuple[str, Path]:
        """Creates an importable package with the given files."""
        name = f"patera_test_app_{next(_counter)}"
        root = self.tmp_path / name
        root.mkdir()
        (root / "__init__.py").write_text("")
        for rel, content in (files or {}).items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(textwrap.dedent(content).lstrip("\n"))
        importlib.invalidate_caches()
        importlib.import_module(name)
        self.packages.append(name)
        return name, root

    def __call__(
        self,
        *,
        controllers: Iterable[type] = (),
        exception_handlers: Iterable[type] = (),
        middleware: Iterable[type] = (),
        extensions: Iterable[type] = (),
        files: Optional[dict[str, str]] = None,
        cli_mode: bool = False,
        app_base: Optional[type] = None,
        **config: Any,
    ) -> Patera[Any]:
        name, root = self.package(files)

        config.setdefault("DEFAULT_LOGGER", QUIET_LOGGER)
        config.setdefault("LOG_FILES", SYNC_LOG_FILES)
        config.setdefault("APP_NAME", "Test app")
        config.setdefault("STARTUP_BANNER", False)
        annotations = {key: Any for key in config}
        config_cls = type(
            "TestConfig",
            (BaseConfig,),
            {
                "__annotations__": {"BASE_PATH": str, **annotations},
                "BASE_PATH": str(root),
                **config,
                "__module__": name,
            },
        )

        namespace: dict[str, Any] = {
            "__module__": name,
            "app_extensions": list(extensions),
        }
        base = app_base or Patera
        app_cls = app_decorator(name, configs=config_cls)(
            type("TestApp", (base,), namespace)
        )
        application = app_cls(cli_mode=cli_mode)

        for handler in exception_handlers:
            application.register_exception_handler(handler)
        for mw in middleware:
            application.register_middleware(mw)
        if controllers:
            application.register_controller(*controllers)

        self.apps.append(application)
        return application

    def cleanup(self) -> None:
        for application in self.apps:
            application._remove_logger_sinks()
        for name in self.packages:
            for mod in list(sys.modules):
                if mod == name or mod.startswith(name + "."):
                    del sys.modules[mod]


def make_scope(
    method: str = "GET",
    path: str = "/",
    *,
    query_string: bytes = b"",
    headers: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "scheme": "http",
        "query_string": query_string,
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (headers or {}).items()
        ],
        "client": ("127.0.0.1", 1234),
    }


def make_receive(*chunks: bytes, disconnect: bool = False):
    """ASGI receive callable yielding the given body chunks."""
    messages: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        messages.append(
            {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        )
    if disconnect:
        if messages:
            messages[-1]["more_body"] = True
        messages.append({"type": "http.disconnect"})
    if not messages:
        messages.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    return receive


def make_request(
    application: Patera[Any],
    method: str = "GET",
    path: str = "/",
    *,
    body: bytes = b"",
    headers: Optional[dict[str, str]] = None,
    query_string: bytes = b"",
    route_parameters: Optional[dict[str, Any]] = None,
    disconnect: bool = False,
):
    from patera.request import Request

    sent: list[dict[str, Any]] = []

    async def send(message):
        sent.append(message)

    chunks = (body,) if body else ()
    req = Request(
        make_scope(method, path, query_string=query_string, headers=headers),
        make_receive(*chunks, disconnect=disconnect),
        send,
        application,
        dict(route_parameters or {}),
        lambda: None,
    )
    req.sent_messages = sent  # type: ignore[attr-defined]
    return req
