"""
Admin extension controller
"""

from typing import Any, cast

import os
import mimetypes
from werkzeug.security import safe_join

from patera.utilities import get_file, get_range_file
from patera.controller import Controller, get, before_request
from patera import Patera, Request, Response, HttpStatus
from patera.auth import role_required

from .admin_interface import AdminInterface, Permissions
from .exceptions import UnsupportedLanguage


class _AdminController(Controller[Patera]):
    """
    Admin controller
    """

    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @before_request
    async def check_language(self, req: Request):
        lang = cast(str, req.route_parameters.get("lang"))
        if lang not in self.admin_interface.supported_languages:
            raise UnsupportedLanguage(lang)

    @get("/")
    async def login(self, req: Request) -> Response:
        """
        Login page
        """
        return await req.res.html(
            "_admin/login.html",
            {
                **self.context_variables,
                "login_media_type": self.admin_interface.configs.LOGIN_MEDIA_TYPE.lower(),
                "dashboard_url": self.admin_interface.url_for(
                    "_AdminController.dashboard"
                ),
            },
        )

    @get("/dashboard")
    @role_required(Permissions.ADMIN_CAN_ENTER)
    async def dashboard(self, req: Request) -> Response:
        """
        Admin dashboard page
        """
        return await req.res.html(
            "_admin/dashboard.html",
            {**self.context_variables, "logs": self.app.log_buffer},
        )

    @get("/_static/<path:filename>")
    async def static(self, req: Request, filename: str) -> Response:
        """
        Endpoint for static files with HTTP Range support,
        falling back to get_file for full-content requests.
        """
        # Checks if file exists
        file_path = None
        candidate = safe_join(self.admin_interface.admin_root_path, "static", filename)
        if candidate and os.path.exists(candidate):
            file_path = candidate
        if not file_path:
            return req.res.no_content().status(HttpStatus.NOT_FOUND)

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

    @property
    def context_variables(self) -> dict[str, Any]:
        return {
            "translate": self.admin_interface.translate,
            "lang": self.admin_interface.current_language,
            "logo_url": self.admin_interface.logo_url,
            "admin_interface": self.admin_interface,
            "admin_url_for": self.admin_interface.url_for,
            "url_for_for_login": self.admin_interface.configs.URL_FOR_FOR_LOGIN,
            "url_for_for_logut": self.admin_interface.configs.URL_FOR_FOR_LOGOUT,
            "url_for_for_logut_redirect": self.admin_interface.configs.URL_FOR_FOR_LOGOUT_REDIRECT,
        }

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
