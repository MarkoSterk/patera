"""Admin extension exception handler"""

from typing import cast

from patera.exceptions import ExceptionHandler, handles
from patera import Patera, Request, Response, HttpStatus

from .exceptions import UnsupportedLanguage, MissingPermission
from .admin_interface import AdminInterface


class _AdminExceptionHandler(ExceptionHandler[Patera]):
    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @handles(UnsupportedLanguage)
    async def unsupported_lang_exc(
        self, req: Request, exc: UnsupportedLanguage
    ) -> Response:
        return req.res.json(
            {
                "message": f"Unsupported language detected: {exc.lang}. Supported languages are: {self.admin_interface.supported_languages}",
                "status": "error",
            }
        ).status(HttpStatus.BAD_REQUEST)

    @handles(MissingPermission)
    async def missing_permission_exc(
        self, req: Request, exc: MissingPermission
    ) -> Response:
        return req.res.json(
            {
                "message": f"Missing required permission for '{exc.permission}'",
                "status": "error",
            }
        ).status(HttpStatus.UNAUTHORIZED)

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
