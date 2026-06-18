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
from patera.auth import role_required, login_required
from patera.static import static_resource

from .admin_interface import AdminInterface, Permissions
from .exceptions import (
    AdminUnsupportedLanguage,
    AdminLoginRequiredException,
    AdminAuthorizationRequiredException,
)
from .schemas.dashboard_schemas import LogsQuerySchema


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
            raise AdminUnsupportedLanguage(lang)

    @get("/")
    async def login(self, req: Request) -> Response:
        """
        Login page
        """
        return await req.res.html(
            "_admin/login.html",
            {
                **self.admin_interface.context_variables,
                "login_media_type": self.admin_interface.configs.LOGIN_MEDIA_TYPE.lower(),
                "dashboard_url": self.admin_interface.url_for(
                    "_AdminController.dashboard"
                ),
            },
        )

    @get("/dashboard")
    @role_required(
        Permissions.ADMIN_CAN_ENTER,
        raise_authentication_exception=AdminLoginRequiredException,
        raise_authorization_exception=AdminAuthorizationRequiredException,
    )
    async def dashboard(self, req: Request) -> Response:
        """
        Admin dashboard page
        """
        query_schema = LogsQuerySchema(**req.query_parameters)  # type: ignore

        logs: list[dict[str, Any]] = list(self.app.log_buffer.get_all())

        if query_schema.query is not None and query_schema.query.strip():
            logs = [
                log for log in logs if self.filter_log_messages(log, query_schema.query)
            ]

        reverse: bool = query_schema.order_by.startswith("-")
        order_by: str = (
            query_schema.order_by[1:]
            if query_schema.order_by.startswith("-")
            else query_schema.order_by
        )

        logs = sorted(
            logs,
            key=lambda log: self.get_order_value(log, order_by),
            reverse=reverse,
        )

        total_logs = len(logs)
        page = max(query_schema.page, 1)
        count = max(query_schema.count, 1)

        total_pages = max((total_logs + count - 1) // count, 1)

        if page > total_pages:
            page = total_pages

        paginated_logs = self.paginate_logs(
            logs=logs,
            page=page,
            count=count,
        )

        return await req.res.html(
            "_admin/dashboard.html",
            {
                **self.admin_interface.context_variables,
                "log_entries": paginated_logs,
                "logs_total": total_logs,
                "logs_page": page,
                "logs_count": count,
                "logs_total_pages": total_pages,
                "logs_order_by": query_schema.order_by,
                "logs_query": query_schema.query or "",
            },
        )

    @get("/unauthorized")
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def unauthorized_entry(self, req: Request) -> Response:
        return await req.res.html(
            "_admin/unauthorized_entry.html", {**self.admin_interface.context_variables}
        )

    @get("/_static/<path:filename>")
    @static_resource
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

    def filter_log_messages(self, log: dict[str, Any], query: str) -> bool:
        msg: str = str(log.get("message", "")).lower()
        logger_name: str = str(log.get("logger_name", "")).lower()
        name: str = str(log.get("name", "")).lower()
        file: str = str(log.get("file", "")).lower()
        function: str = str(log.get("function", "")).lower()
        level: str = str(log.get("level", "")).lower()
        line: str = str(log.get("line", "")).lower()
        time: str = str(log.get("time", "")).lower()

        query = query.lower()

        return (
            query in msg
            or query in logger_name
            or query in name
            or query in file
            or query in function
            or query in level
            or query in line
            or query in time
        )

    def get_order_value(self, log: dict[str, Any], order_by: str) -> Any:
        value = log.get(order_by)

        if value is None:
            return ""

        return value

    def paginate_logs(
        self,
        logs: list[dict[str, Any]],
        page: int,
        count: int,
    ) -> list[dict[str, Any]]:
        page = max(page, 1)
        count = max(count, 1)

        start = (page - 1) * count
        end = start + count

        return logs[start:end]

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
