"""Admin extension exception handler"""

from patera.exceptions import ExceptionHandler, handles
from patera import Patera, Request, Response, HttpStatus
from patera.injectable import Inject

from .exceptions import UnsupportedLanguage
from .admin_interface import AdminInterface


class _AdminExceptionHandler(ExceptionHandler[Patera]):
    admin_interface: Inject[AdminInterface]

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
