"""Frontend extension"""

from __future__ import annotations
import os
import json
import compileall
import mimetypes
from typing import cast, Type, TypedDict, NotRequired
from werkzeug.security import safe_join
import zipfile
from pathlib import Path
from pydantic import BaseModel, Field
from pyjolt.utilities import get_file, get_range_file
from pyjolt.controller import Controller, get, path
from pyjolt import PyJolt, BaseExtension, Request, Response, HttpStatus


class FrontendController(Controller):
    _frontend: "Frontend"

    @get("/<path:filename>")
    async def static(self, req: Request, filename: str) -> Response:
        """
        Frontend static controller. Serves frontend core files and user files
        """
        # Checks if file exists
        file_path = None
        candidate = safe_join(self._frontend._this_root, "_static", filename)
        print("CANDIDATE 1: ", candidate)
        if candidate and os.path.exists(candidate):
            file_path = candidate
        else:
            candidate = safe_join(
                self.app.root_path, self._frontend._frontend_path, filename
            )
            print("CANDIDATE 2: ", candidate)
            if candidate and os.path.exists(candidate):
                file_path = candidate

        if file_path is None:
            return req.res.no_content().status(HttpStatus.NOT_FOUND)
        print("SENDING FILE: ", file_path)
        # checks/guesses mimetype
        guessed, _ = mimetypes.guess_type(file_path)
        content_type = guessed or "application/octet-stream"

        # Checks range header and returns range if header is present
        range_header = req.headers.get("range")
        if not range_header:
            status, headers, body = await get_file(file_path, content_type=content_type)
            headers["Accept-Ranges"] = "bytes"
            return req.res.send_file(body, headers).status(status)

        return await get_range_file(req.res, file_path, range_header, content_type)


class _FrontendConfigs(BaseModel):
    APP_PATH: str = Field(
        "frontend_app",
        description="Relative path of the frontend application relative to the pyjolt app",
    )
    CONTROLLER_PATH: str = Field(
        "/__frontend__", description="URL path of the frontend controller"
    )


class FrontendConfigs(TypedDict):
    APP_PATH: NotRequired[str]
    CONTROLLER_PATH: NotRequired[str]


class Frontend(BaseExtension):
    def __init__(self, configs_name: str = "FRONTEND") -> None:
        """Init method"""
        self._configs_name = configs_name
        self._frontend_path: str
        self._controller_url: str
        self._this_root = os.path.dirname(__file__)

    def init_app(self, app: PyJolt) -> None:
        self._app = app
        configs: dict[str, str] = self._app.get_conf(self._configs_name, {})
        configs = _FrontendConfigs.model_validate(configs).model_dump()
        self._frontend_path = cast(str, configs.get("APP_PATH"))
        self._controller_url = cast(str, configs.get("CONTROLLER_PATH"))
        ctrl: Type[FrontendController] = path(self._controller_url)(FrontendController)

        setattr(ctrl, "_frontend", self)
        self.app.register_controller(ctrl)
        self.build_zip()

    def build_zip(self):
        PYJOLT_ROOT = Path(self.app_this_path)
        FRONTEND_PACKAGE = PYJOLT_ROOT / "frontend"
        ROOT = Path(self.app.root_path)
        SRC = ROOT / self._frontend_path
        SRC_FILES = SRC
        SRC_FILES.mkdir(parents=True, exist_ok=True)
        DIST = SRC / "__dist__"
        OUT = DIST / "pyjolt_app.zip"
        DIST.mkdir(parents=True, exist_ok=True)
        compileall.compile_dir(str(SRC))

        DIST.mkdir(exist_ok=True)
        with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("pyjolt/__init__.py", "")
            for p in FRONTEND_PACKAGE.rglob("*"):
                if p.is_file():
                    arcname = p.relative_to(PYJOLT_ROOT.parent).as_posix()
                    z.write(p, arcname)

            for p in SRC_FILES.rglob("*"):
                if p.is_file():
                    arcname = p.relative_to(SRC).as_posix()
                    z.write(p, f"frontend/{arcname}")

        self.create_json_config(DIST)

    def create_json_config(self, DIST: Path) -> None:
        zip_file_url: str = self.app.url_for(
            "FrontendController.static", filename="__dist__/pyjolt_app.zip"
        )
        configs = {"files": {zip_file_url: "pyjolt_app.zip"}}
        path = DIST / "conf.json"
        with open(path, "w", encoding="utf-8") as file:
            file.write(json.dumps(configs))

    def include(self) -> str:
        main_file_url: str = self.app.url_for(
            "FrontendController.static", filename="_main.py"
        )
        conf_file_url: str = self.app.url_for(
            "FrontendController.static", filename="__dist__/conf.json"
        )
        custom_js_url: str = self.app.url_for(
            "FrontendController.static", filename="__pyjolt_custom.js"
        )

        print("CUSTOM JS URL: ", custom_js_url)

        return f"""
            <script src="{custom_js_url}"></script>
            <script type="py" config="{conf_file_url}" src="{main_file_url}"></script>
        """

    @property
    def app_this_path(self) -> str:
        return self.app._this_path
