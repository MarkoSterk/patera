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
from patera.injectable import Inject

from .admin_interface import AdminInterface
from .exceptions import UnsupportedLanguage


class _AdminController(Controller[Patera]):
    """
    Admin controller
    """

    admin_interface: Inject[AdminInterface]

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
                "url_for_for_login": self.admin_interface.configs.URL_FOR_FOR_LOGIN,
                "dashboard_url": self.admin_interface.url_for(
                    "_AdminController.dashboard"
                ),
            },
        )

    @get("/dashboard")
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
        }
