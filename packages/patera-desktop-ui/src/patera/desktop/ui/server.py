"""Optional host extension: shell, immutable assets, build CLI and API guard."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
import sys
import threading
from html import escape
from pathlib import Path
from typing import ClassVar, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from patera import HttpStatus, BaseExtension, MiddlewareBase, Request, Response
from patera.cli import CLIController, cli_controller, command
from patera.controller import Controller, get, path, post
from patera.exceptions.http_exceptions import StaticAssetNotFound
from patera.utilities import file_response

from .build import build, lock_runtime


class DesktopUIConfig(BaseModel):
    SOURCE: str = "../frontend"
    ENTRYPOINT: str = "frontend:app"
    RUNTIME: str = "../ui-runtime"
    OUTPUT: str = "../build/ui"
    MOUNT: str = "/app"
    ASSETS: str = "/__ui__"
    TITLE: str = "Patera"
    PUBLIC: dict[str, Any] = Field(default_factory=dict)
    API_PATHS: list[str] = Field(default_factory=lambda: ["/api"])
    SERVER_COMPONENTS_PATH: str | None = None
    SERVER_COMPONENTS: dict[str, str] = Field(default_factory=dict)

    @field_validator("MOUNT", "ASSETS")
    @classmethod
    def validate_mount(cls, value):
        if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+", value):
            raise ValueError("Use a non-root URL path without a trailing slash")
        return value

    @field_validator("API_PATHS")
    @classmethod
    def validate_api_paths(cls, values):
        for value in values:
            cls.validate_mount(value)
        return values

    @model_validator(mode="after")
    def separate_mounts(self):
        paths = [self.MOUNT, self.ASSETS, *self.API_PATHS]
        for index, first in enumerate(paths):
            for second in paths[index + 1 :]:
                if (
                    first == second
                    or first.startswith(second + "/")
                    or second.startswith(first + "/")
                ):
                    raise ValueError(
                        "UI, asset and protected API mounts must not overlap"
                    )
        json.dumps(self.PUBLIC, allow_nan=False)
        if self.SERVER_COMPONENTS_PATH:
            self.validate_mount(self.SERVER_COMPONENTS_PATH)
            if not any(
                _within(self.SERVER_COMPONENTS_PATH, prefix)
                for prefix in self.API_PATHS
            ):
                raise ValueError("Server components must use a protected API path")
        elif self.SERVER_COMPONENTS:
            raise ValueError("SERVER_COMPONENTS requires SERVER_COMPONENTS_PATH")
        return self


def _within(pathname, prefix):
    return pathname == prefix or pathname.startswith(prefix + "/")


class DesktopUIGuard(MiddlewareBase):
    _middleware: ClassVar[bool] = True
    _order_: ClassVar[int] = -110

    async def middleware(self, req: Request) -> Response:
        extension = req.app.get_extension(DesktopUI)
        pathname = req.scope["path"]
        protected = any(
            _within(pathname, req.app.url_prefix + p)
            for p in extension.configs.API_PATHS
        )
        shell = _within(pathname, extension.mount)
        if protected or shell:
            host = req.headers.get("host", "")
            try:
                hostname = urlsplit("http://" + host).hostname
            except ValueError:
                hostname = None
            if hostname not in {"127.0.0.1", "localhost", "::1"}:
                return req.res.text("Desktop UI requires a loopback host").status(
                    HttpStatus.FORBIDDEN
                )
            origin = req.headers.get("origin")
            expected = req.scope.get("scheme", "http") + "://" + host
            if origin and origin != expected:
                return req.res.text("Cross-origin desktop request rejected").status(
                    HttpStatus.FORBIDDEN
                )
            if req.headers.get("sec-fetch-site") == "cross-site":
                return req.res.text("Cross-site desktop request rejected").status(
                    HttpStatus.FORBIDDEN
                )
            if protected and not hmac.compare_digest(
                req.headers.get("x-patera-ui-token", "").encode(),
                extension.token.encode(),
            ):
                return req.res.text("Desktop UI session required").status(
                    HttpStatus.FORBIDDEN
                )
        return await self.next(req)


class DesktopUI(BaseExtension[Any, DesktopUIConfig]):
    def init(self):
        self.token = secrets.token_urlsafe(32)
        self.mount = self.app.url_prefix + self.configs.MOUNT
        self.assets = self.app.url_prefix + self.configs.ASSETS
        self.app.register_middleware(DesktopUIGuard)
        self.app.register_cli_controller(DesktopUICLI(self.app, self))
        # Fresh classes per application; no shared class mutation or extension state.
        extension = self
        self.server_components = {
            key: (value, None) for key, value in self.configs.SERVER_COMPONENTS.items()
        }
        if self.configs.SERVER_COMPONENTS_PATH:

            @path(self.configs.SERVER_COMPONENTS_PATH, open_api_spec=False)
            class DesktopUIComponents(Controller):
                @post("")
                async def render_component(self, req: Request) -> Response:
                    from .lifecycle import invoke

                    payload = await req.json()
                    if not isinstance(payload, dict):
                        return req.res.text("Expected component request").status(
                            HttpStatus.BAD_REQUEST
                        )
                    tag = payload.get("tag_name")
                    group = payload.get("group_name", "default")
                    if not isinstance(tag, str) or not isinstance(group, str):
                        return req.res.text("Invalid component name").status(
                            HttpStatus.BAD_REQUEST
                        )
                    entry = extension.server_components.get(group + "/" + tag)
                    if entry is None:
                        return req.res.text("Unknown server component").status(
                            HttpStatus.NOT_FOUND
                        )
                    for key in ("attributes", "route_parameters", "query_parameters"):
                        if not isinstance(payload.get(key, {}), dict):
                            return req.res.text("Invalid component arguments").status(
                                HttpStatus.BAD_REQUEST
                            )
                    template_name, factory = entry
                    values = await invoke(factory, req, payload) if factory else {}
                    compiled = extension.app.jinja_environment.get_template(
                        template_name
                    )
                    markup = await compiled.render_async(
                        args=payload.get("attributes", {}),
                        params=payload.get("route_parameters", {}),
                        query=payload.get("query_parameters", {}),
                        **values,
                    )
                    return req.res.html_body(markup)

            self.app.register_controller(DesktopUIComponents)

        @path(self.configs.MOUNT, open_api_spec=False)
        class DesktopUIShell(Controller):
            @get("/")
            async def index(self, req: Request) -> Response:
                return extension.shell(req)

            @get("/<path:page_path>")
            async def page(self, req: Request, page_path: str) -> Response:
                return extension.shell(req)

        @path(self.configs.ASSETS, open_api_spec=False)
        class DesktopUIAssets(Controller):
            @get("/version")
            async def version(self, req: Request) -> Response:
                if not extension.app.configs.DEBUG or getattr(sys, "frozen", False):
                    raise StaticAssetNotFound()
                req.res.set_header("Cache-Control", "no-store")
                return req.res.json({"id": extension.manifest()["id"]})

            @get("/<path:filename>")
            async def asset(self, req: Request, filename: str) -> Response:
                return extension.asset(req, filename)

        self.app.register_controller(DesktopUIShell, DesktopUIAssets)

    def register_server_component(
        self, tag, template, *, group="default", context=None
    ):
        if not self.configs.SERVER_COMPONENTS_PATH:
            raise ValueError("Configure SERVER_COMPONENTS_PATH first")
        key = group + "/" + tag
        if key in self.server_components:
            raise ValueError(f"Duplicate server component: {key}")
        self.server_components[key] = (template, context)

    def paths(self):
        root = Path(self.app.root_path)
        return tuple(
            (root / value).resolve()
            for value in (
                self.configs.SOURCE,
                self.configs.RUNTIME,
                self.configs.OUTPUT,
            )
        )

    @property
    def output(self):
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / "patera_ui"
        return self.paths()[2]

    def build(self):
        if getattr(sys, "frozen", False):
            raise RuntimeError("Packaged applications serve prebuilt UI assets")
        return build(
            *self.paths(), entrypoint=self.configs.ENTRYPOINT, asset_url=self.assets
        )

    def manifest(self):
        try:
            return json.loads(
                (self.output / "current.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "UI build missing. Run 'patera cli ui:build' before starting."
            ) from error

    def shell(self, req):
        manifest = self.manifest()
        base = self.assets + "/" + manifest["id"]
        public = {
            "mount": self.mount,
            "api_prefix": self.app.url_prefix,
            "server_components_url": self.configs.SERVER_COMPONENTS_PATH,
            "token": self.token,
            "public": self.configs.PUBLIC,
            "assets": base + "/public",
            "build_id": manifest["id"],
            "reload_url": (self.assets + "/version")
            if self.app.configs.DEBUG and not getattr(sys, "frozen", False)
            else None,
        }
        data = (
            json.dumps(public, ensure_ascii=True)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        core = base + "/runtime/" + manifest["runtime"]["pyscript"]
        body = f'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(self.configs.TITLE)}</title></head><body>
<main id="app" aria-live="polite">Loading…</main>
<script id="patera-ui-config" type="application/json">{data}</script>
<script src="{escape(base)}/adapter.js" type="module"></script>
<script src="{escape(core)}" type="module"></script>
<script type="py" src="{escape(base)}/bootstrap.py" config="{escape(base)}/config.json"></script>
</body></html>'''
        req.res.set_headers(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
            }
        )
        return req.res.html_body(body)

    def asset(self, req, filename):
        build_id, separator, relative = filename.partition("/")
        if not separator or not re.fullmatch(r"[0-9a-f]{24}", build_id):
            raise StaticAssetNotFound()
        folder = self.output / build_id
        try:
            manifest = json.loads(
                (folder / "manifest.json").read_text(encoding="utf-8")
            )
            if relative not in manifest["files"]:
                raise StaticAssetNotFound()
            # Containment applies even if a developer later adds a symlink.
            from .build import safe_relative

            candidate = folder.joinpath(*safe_relative(relative).parts)
            if (
                not candidate.resolve().is_relative_to(folder.resolve())
                or not candidate.is_file()
            ):
                raise StaticAssetNotFound()
        except (FileNotFoundError, ValueError):
            raise StaticAssetNotFound() from None
        req.res.set_headers(
            {
                "Cache-Control": "public, max-age=31536000, immutable",
                "X-Content-Type-Options": "nosniff",
            }
        )
        return file_response(
            req.res,
            str(candidate),
            req.headers,
            cache_control="public, max-age=31536000, immutable",
        )

    def desktop_packaging(self, spec_file):
        base = Path(spec_file).resolve().parent
        source, runtime, output = self.paths()
        if source.is_relative_to(Path(self.app.root_path).resolve()):
            raise ValueError(
                "Desktop UI SOURCE must be outside the backend application package "
                "so PyInstaller does not import browser code as native Python"
            )
        return {
            "builder": "patera.desktop.ui.build:prepare_package",
            "options": {
                "source": os.path.relpath(source, base),
                "runtime": os.path.relpath(runtime, base),
                "output": os.path.relpath(output, base),
                "entrypoint": self.configs.ENTRYPOINT,
                "asset_url": self.assets,
            },
        }


@cli_controller(name="ui")
class DesktopUICLI(CLIController):
    def __init__(self, app, extension):
        self.extension = extension
        super().__init__(app)

    @command("build", help="Build the offline browser UI")
    async def build(self):
        manifest = self.extension.build()
        print(f"Built UI {manifest['id']} in {self.extension.output}")

    @command("watch", help="Rebuild changed UI sources; development windows reload")
    async def watch(self):
        stop = threading.Event()
        worker = threading.Thread(
            target=self._watch, args=(stop,), name="patera-ui-watch"
        )
        worker.start()
        try:
            while worker.is_alive():
                await asyncio.sleep(0.5)
        finally:
            stop.set()
            worker.join()

    @command("run", help="Build UI and open desktop; watch in dev mode (dev or prod)")
    async def run(self, mode: str = "dev") -> None:
        from patera.desktop import Desktop

        if mode not in {"dev", "prod"}:
            raise ValueError("Mode must be 'dev' or 'prod'.")
        desktop = self.app.get_extension(Desktop)
        # Snapshot before building so edits made during the build are not missed.
        previous = self._snapshot() if mode == "dev" else None
        await self.build()
        stop = threading.Event()
        worker = None
        try:
            if mode == "dev":
                worker = threading.Thread(
                    target=self._watch, args=(stop, previous), name="patera-ui-watch"
                )
                worker.start()
            # GUI toolkits require the main thread; Desktop owns server cleanup.
            desktop.run(mode)
        finally:
            stop.set()
            if worker is not None:
                worker.join()

    def _snapshot(self):
        source, runtime, _ = self.extension.paths()
        roots = (source, runtime, Path(__file__).parent)
        return tuple(
            (str(file), file.stat().st_mtime_ns, file.stat().st_size)
            for root in roots
            for file in sorted(root.rglob("*"))
            if file.is_file() and "__pycache__" not in file.parts
        )

    def _watch(self, stop, previous=None):
        while not stop.is_set():
            try:
                current = self._snapshot()
                if current != previous:
                    previous = current
                    manifest = self.extension.build()
                    print(f"Built UI {manifest['id']}", flush=True)
            except Exception as error:
                print(f"UI build failed (previous build retained): {error}", flush=True)
            stop.wait(0.5)

    @command("lock-runtime", help="Hash a complete local PyScript/Pyodide runtime")
    async def lock_runtime(
        self,
        pyscript: str,
        interpreter: str,
        pyscript_version: str,
        pyodide_version: str,
        python_version: str,
    ):
        manifest = lock_runtime(
            self.extension.paths()[1],
            pyscript=pyscript,
            interpreter=interpreter,
            pyscript_version=pyscript_version,
            pyodide_version=pyodide_version,
            python_version=python_version,
        )
        print(f"Locked runtime in {manifest}")
