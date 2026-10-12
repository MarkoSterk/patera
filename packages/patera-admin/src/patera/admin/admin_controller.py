"""
Admin extension controller
"""

from typing import Any, cast

import os
from werkzeug.security import safe_join

from patera.exceptions import StaticAssetNotFound
from patera.utilities import file_response
from patera.controller import Controller, get, post, before_request
from patera import Patera, Request, Response
from patera.auth import role_required, login_required
from patera.static import static_resource

from .admin_interface import AdminInterface, Permissions
from .exceptions import (
    AdminUnsupportedLanguage,
    AdminLoginRequiredException,
    AdminAuthorizationRequiredException,
)
from .schemas.dashboard_schemas import (
    LOG_LEVELS,
    LogsQuerySchema,
    level_at_least,
    log_sort_key,
)
from .admin_interface import NOTIFICATIONS_SEEN_COOKIE


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

        logs: list[dict[str, Any]] = await self.app.log_files.read_async()

        logs = [log for log in logs if level_at_least(log, query_schema.severity)]

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
            key=lambda log: log_sort_key(log, order_by),
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
                "logs_severity": query_schema.severity,
                "log_levels": list(LOG_LEVELS),
                "log_files_enabled": self.app.log_files.enabled,
            },
        )

    @get("/notifications")
    @role_required(
        Permissions.ADMIN_CAN_ENTER,
        raise_authentication_exception=AdminLoginRequiredException,
        raise_authorization_exception=AdminAuthorizationRequiredException,
    )
    async def notifications(self, req: Request) -> Response:
        """
        Notifications for the Admin header, newest first, with the number
        this browser has not marked as read.
        """
        items = await self.admin_interface.notifications()
        seen_at = self.admin_interface.notifications_seen_at(req)
        return req.res.json(
            {
                "status": "success",
                "message": "Notifications",
                "data": {
                    "enabled": self.app.log_files.enabled,
                    "unread": self.admin_interface.count_unread(items, seen_at),
                    "items": items,
                },
            }
        )

    @post("/notifications/seen")
    @role_required(
        Permissions.ADMIN_CAN_ENTER,
        raise_authentication_exception=AdminLoginRequiredException,
        raise_authorization_exception=AdminAuthorizationRequiredException,
    )
    async def notifications_seen(self, req: Request) -> Response:
        """Marks every current notification as read for this browser."""
        items = await self.admin_interface.notifications(limit=1)
        res = req.res.json(
            {"status": "success", "message": "Notifications marked as read"}
        )
        if items and items[0]["time"]:
            res.set_cookie(
                NOTIFICATIONS_SEEN_COOKIE,
                str(items[0]["time"]),
                max_age=365 * 24 * 3600,
                path=self.app._app_base_url
                + self.admin_interface.configs.ADMIN_BASE_URL,
            )
        return res

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
        Serves Admin's own assets, streamed from disk, with conditional
        requests and HTTP Range support. A missing file is a JSON 404.
        """
        candidate = safe_join(self.admin_interface.admin_root_path, "static", filename)
        if not candidate or not os.path.isfile(candidate):
            raise StaticAssetNotFound()
        return file_response(req.res, candidate, req.headers)

    def filter_log_messages(self, log: dict[str, Any], query: str) -> bool:
        msg: str = str(log.get("message", "")).lower()
        logger_name: str = str(log.get("logger_name", "")).lower()
        name: str = str(log.get("name", "")).lower()
        file: str = str(log.get("file", "")).lower()
        function: str = str(log.get("function", "")).lower()
        level: str = str(log.get("level", "")).lower()
        line: str = str(log.get("line", "")).lower()
        time: str = str(log.get("time", "")).lower()
        exception: str = str(log.get("exception", "")).lower()

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
            or query in exception
        )

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
