"""Admin extension exception handler"""

from typing import cast

from patera.exceptions import ExceptionHandler, handles, exception_handler
from patera import Patera, Request, Response, HttpStatus

from .exceptions import (
    AdminUnsupportedLanguage,
    AdminMissingPermission,
    AdminLoginRequiredException,
    AdminAuthorizationRequiredException,
    AdminUnknownEmailClientException,
)
from .admin_interface import AdminInterface, Permissions


@exception_handler
class _AdminExceptionHandler(ExceptionHandler[Patera]):
    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @handles(AdminUnsupportedLanguage)
    async def unsupported_lang_exc(
        self, req: Request, exc: AdminUnsupportedLanguage
    ) -> Response:
        return req.res.json(
            {
                "message": f"Unsupported language detected: {exc.lang}. Supported languages are: {self.admin_interface.supported_languages}",
                "status": "error",
            }
        ).status(HttpStatus.BAD_REQUEST)

    @handles(AdminMissingPermission)
    async def missing_permission_exc(
        self, req: Request, exc: AdminMissingPermission
    ) -> Response:
        return req.res.json(
            {
                "message": f"Missing required permission for '{exc.permission}'",
                "status": "error",
            }
        ).status(HttpStatus.UNAUTHORIZED)

    @handles(AdminLoginRequiredException)
    async def login_required_exc(
        self, req: Request, exc: AdminLoginRequiredException
    ) -> Response:
        return req.res.redirect(
            self.admin_interface.url_for(
                "_AdminController.login", lang=self.admin_interface.current_language
            )
        )

    @handles(AdminAuthorizationRequiredException)
    async def authorization_required_exc(
        self, req: Request, exc: AdminAuthorizationRequiredException
    ) -> Response:
        if req.headers.get("content-type", "text/html").lower() == "text/html":
            if Permissions.ADMIN_CAN_ENTER in exc.roles:
                return req.res.redirect(
                    self.admin_interface.url_for("_AdminController.unauthorized_entry")
                )
            return (
                await req.res.html(
                    "_admin/error.html",
                    {
                        **self.admin_interface.context_variables,
                        "error_title": "Unauthorized",
                        "error_message": "Missing authorization for action.",
                        "error_status": exc.msg,
                        "status_code": HttpStatus.UNAUTHORIZED,
                        "error_details": None,
                    },
                )
            ).status(HttpStatus.UNAUTHORIZED)
        return req.res.json(
            {"message": "Missing required role", "status": "success"}
        ).status(HttpStatus.UNAUTHORIZED)

    @handles(AdminUnknownEmailClientException)
    async def unknown_email_client(
        self, req: Request, exc: AdminUnknownEmailClientException
    ) -> Response:

        return req.res.json(
            {
                "message": f"Email Client with sender email {exc.email} does not exist.",
                "status": "error",
            }
        ).status(HttpStatus.BAD_REQUEST)

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
