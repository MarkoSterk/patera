"""
Turns exceptions raised while handling a request into responses, with
the application's exception handlers or the default responses.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

from typing import (
    Callable,
    Optional,
)


from ..exceptions.http_exceptions import (
    BaseHttpException,
    HtmlAborterException,
    StaticPageNotFound,
)
from ..http_methods import HttpMethod
from ..request import Request
from ..response import Response
from ..utilities import (
    run_sync_or_async,
)
from ..response_renderer import ResponseRendererException

from ._base import AppPart
from .http import without_body


class ExceptionResolver(AppPart):
    """
    Turns exceptions raised while handling a request into responses, with
    the application's exception handlers or the default responses.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    async def send_exception_response(self, req: Request, exc: Exception) -> None:
        """
        Answers an exception raised before the response started, with the
        application's handler for it or with the default response. An
        exception without either is raised again, as an unhandled error.
        """
        app = self._app
        req.res.reset()

        if isinstance(exc, ResponseRendererException):
            raise exc

        if isinstance(exc, HtmlAborterException):
            handler = app._find_exception_handler(exc, stop_at=HtmlAborterException)
            if handler is None:
                res = (await req.res.html(exc.template, context=exc.data)).status(
                    exc.status_code
                )
                return await app.send_response(res, req.send, None)
        elif isinstance(exc, StaticPageNotFound):
            handler = app._find_exception_handler(exc, stop_at=StaticPageNotFound)
            if handler is None:
                send = req.send
                if req.method == HttpMethod.HEAD.value:
                    send = without_body(send)
                return await app.abort_route_not_found(send)
        else:
            handler = app._find_exception_handler(exc)

        if handler is not None:
            res = await run_sync_or_async(handler, req, exc)
        else:
            default_res = app.default_exception_response(req, exc)
            if default_res is None:
                raise exc
            res = default_res

        return await app.send_response(res, req.send, res.expected_body_type())

    def find_exception_handler(
        self,
        exc: BaseException,
        stop_at: Optional[type[BaseException]] = None,
    ) -> Optional[Callable]:
        """
        Returns the registered handler for the exception.

        The exception class hierarchy is walked so that a handler registered
        for a base class (e.g. BaseHttpException) also handles subclasses.
        The most specific handler wins. Handlers are keyed by class, so two
        exception classes that share a name never share a handler.

        ``stop_at`` ends the walk at that class: exceptions with built-in
        handling (html_abort, missing static pages) can be customized by a
        handler for their own class, but are not captured by handlers for
        generic bases such as BaseHttpException.
        """
        app = self._app
        for exc_cls in type(exc).__mro__:
            handler = app._exception_handlers.get(exc_cls)
            if handler is not None:
                return handler
            if exc_cls is stop_at:
                break
        return None

    def default_exception_response(
        self, req: Request, exc: Exception
    ) -> Optional[Response]:
        """
        Fallback responses for exceptions without a registered handler.

        BaseHttpException subclasses (abort(), RequestValidationError from
        @consumes, auth exceptions, ...) become a JSON response with the
        exception's status code.

        Returns None for any other exception, which is then treated as an
        unhandled error (500). That includes a Pydantic ValidationError
        raised outside request-body validation: it is the server's data that
        failed. Override in the app class to customize.
        """
        if isinstance(exc, BaseHttpException):
            return req.res.json(
                {
                    "status": exc.status,
                    "message": exc.message,
                    "data": exc.data,
                }
            ).status(exc.status_code)

        return None
