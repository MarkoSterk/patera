"""Common controller methods"""

# pylint: disable=W0719,W0212
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from pyjolt.exceptions import BaseHttpException
from pyjolt import HttpStatus, Request, Response
from pyjolt.controller import Controller

if TYPE_CHECKING:
    from .admin_dashboard import AdminDashboard


class AdminEnterError(BaseHttpException):
    """Error for when a user does not have permission to enter the dashboard"""

    def __init__(self, user):
        super().__init__(
            "User doesn't have access to admin dashboard",
            HttpStatus.UNAUTHORIZED,
            "error",
            user,
        )


class CommonAdminController(Controller):
    """Admin dashboard controller."""

    _dashboard: "AdminDashboard"

    def get_common_variables(self) -> dict[str, Any]:
        """Creates dictionary with common templating variables"""
        variables: dict[str, Any] = {
            "dashboard": self.dashboard,
            "configs": self.dashboard.configs,
            "all_dbs": self.dashboard.all_dbs,
            "database_models": self.dashboard._databases_models,
            "email_clients": self.dashboard.email_clients,
            "task_managers": self.dashboard.task_managers,
            "format_datetime": self.dashboard.format_datetime,
        }
        return variables

    async def cant_enter_response(self, req: Request) -> Response:
        """Response for when a user cannot enter the dashboard"""
        return (await req.res.html("/__admin_templates/denied_entry.html")).status(
            HttpStatus.UNAUTHORIZED
        )

    async def can_enter(self, req: Request) -> bool:
        """
        Method for checking permission to enter
        admin dashboard
        """
        has_permission: bool = False
        has_permission = await self.dashboard.has_enter_permission(req)
        if not has_permission:
            raise AdminEnterError(req.user)
        return has_permission

    async def extension_not_available(self, req: Request, extension_type: str):
        """Raises an error for unavailable extension"""
        return await req.res.html(
            "/__admin_template/unavailable_extension.html",
            {"extension_name": extension_type},
        )

    @property
    def dashboard(self) -> "AdminDashboard":
        return self._dashboard
