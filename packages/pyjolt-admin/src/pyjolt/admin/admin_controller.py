"""
Main admin dashboard controller module.
Handles login and static files
"""

# pylint: disable=W0719,W0212
from __future__ import annotations

import mimetypes
import os
from typing import TYPE_CHECKING, Any, Optional

from werkzeug.security import safe_join

from pyjolt.http_statuses import HttpStatus

from ..controller import get
from ..auth.authentication import login_required
from ..exceptions.http_exceptions import StaticAssetNotFound
from ..request import Request
from ..response import Response
from ..utilities import get_file, get_range_file
from .common_controller import CommonAdminController
from ..caching import Cache

if TYPE_CHECKING:
    from .admin_dashboard import AdminDashboard


class AdminController(CommonAdminController):
    """Admin dashboard controller."""

    _dashboard: "AdminDashboard"

    @get("/")
    @login_required
    async def index(self, req: Request) -> Response:
        """Index page of dashboard"""
        if not (await self.can_enter(req)):
            return await self.cant_enter_response(req)
        level: str = req.query_params.get("logs", "all")
        logs: list[dict[str, Any]] = (
            self.app.log_buffer.get_all()
            if level == "all"
            else self.app.log_buffer.get_severe()
        )
        logs.reverse()
        caches: Optional[dict[str, Cache]] = self.dashboard.get_cache_interfaces()
        cache_permissions: dict[str, bool] = {}
        if caches is not None:
            for key, cache in caches.items():
                cache_permissions[key] = await self.dashboard.has_cache_permission(
                    req, cache
                )
        return await req.res.html(
            "/__admin_templates/dashboard.html",
            {
                "configs": self.dashboard.configs,
                "all_logs": logs,
                "caches": caches,
                "cache_permissions": cache_permissions,
                **self.get_common_variables(),
            },
        )

    @get("/cache-reset/<string:cache_name>")
    @login_required
    async def reset_cache(self, req: Request, cache_name: str) -> Response:
        """
        Resets cache with provided cache_name
        """
        if not (await self.can_enter(req)):
            return await self.cant_enter_response(req)

        caches: Optional[dict[str, Cache]] = self.dashboard.get_cache_interfaces()
        if caches is None:
            return req.res.json(
                {
                    "message": "No cache extensions found or installed",
                    "status": "danger",
                }
            ).status(HttpStatus.BAD_REQUEST)

        cache: Optional[Cache] = caches.get(cache_name)
        if cache is None:
            return req.res.json(
                {
                    "message": f"No cache extensions matching name {cache_name} found",
                    "status": "warning",
                }
            ).status(HttpStatus.NOT_FOUND)

        if not (await self.dashboard.has_cache_permission(req, cache)):
            return req.res.json(
                {
                    "message": "User doesn't have permission to reset the cache",
                    "status": "danger",
                }
            ).status(HttpStatus.UNAUTHORIZED)

        await cache.clear()

        return req.res.json(
            {"message": "Cache reset successful", "status": "success"}
        ).status(HttpStatus.OK)

    @get("/login")
    async def login(self, req: Request) -> Response:
        """Login route for dashboard"""
        return await req.res.html(
            "/__admin_templates/login.html", {"configs": self.dashboard.configs}
        )

    # STATIC files for dashboard
    @get("/static/<path:filename>")
    async def static(self, req: Request, filename: str) -> Response:
        """Serves static assets for the dashboard"""
        file_path = None
        candidate = safe_join(self.dashboard.root_path, "static", filename)
        if candidate and os.path.exists(candidate):
            file_path = candidate
        if not file_path:
            raise StaticAssetNotFound()

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
