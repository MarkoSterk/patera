from patera import HttpStatus, Request, Response
from patera.exceptions import ExceptionHandler, exception_handler, handles

from app import App
from app.errors import Conflict, ExamError, Forbidden, InvalidCredentials, NotFound


@exception_handler
class ExamExceptionHandler(ExceptionHandler[App]):
    """
    Answers domain errors with Patera's JSON error shape. The most specific
    handler wins, so ``ExamError`` covers any error without its own handler.
    """

    @handles(NotFound)
    async def not_found(self, req: Request, exc: NotFound) -> Response:
        return self._error(req, exc, HttpStatus.NOT_FOUND)

    @handles(Forbidden)
    async def forbidden(self, req: Request, exc: Forbidden) -> Response:
        return self._error(req, exc, HttpStatus.FORBIDDEN)

    @handles(Conflict)
    async def conflict(self, req: Request, exc: Conflict) -> Response:
        return self._error(req, exc, HttpStatus.CONFLICT)

    @handles(InvalidCredentials)
    async def invalid_credentials(
        self, req: Request, exc: InvalidCredentials
    ) -> Response:
        return self._error(req, exc, HttpStatus.UNAUTHORIZED)

    @handles(ExamError)
    async def broken_rule(self, req: Request, exc: ExamError) -> Response:
        return self._error(req, exc, HttpStatus.BAD_REQUEST)

    @staticmethod
    def _error(req: Request, exc: ExamError, status: HttpStatus) -> Response:
        return req.res.json(
            {"status": "error", "message": exc.message, "data": None}
        ).status(status)
