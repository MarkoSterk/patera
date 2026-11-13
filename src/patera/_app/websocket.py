"""
WebSocket request handling: routing, the handler call and closing the
sessions a handler opened.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

from typing import (
    Any,
    Callable,
    cast,
)
from werkzeug.exceptions import NotFound, MethodNotAllowed
from werkzeug.routing import WebsocketMismatch, RequestRedirect


from ..utilities import (
    run_sync_or_async,
)
from ..ctx import request_context

from ._base import AppPart


class WebSocketDispatcher(AppPart):
    """
    WebSocket request handling: routing, the handler call and closing the
    sessions a handler opened.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    async def handle_websocket_request(self, scope, receive, send):
        """
        Handles websocket requests.
        """
        app = self._app
        method: str = "SOCKET"
        url_path: str = scope["path"]

        app._log_request(scope, method, url_path)

        try:
            route_handler, path_kwargs = app._socket_router.match(
                url_path,
                method,
            )

        except NotFound:
            app.logger.info(f"Websocket path {url_path} does not exist")

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket route not found",
                }
            )
            return

        except MethodNotAllowed as exc:
            matching_methods = list(exc.valid_methods or [])

            app.logger.warning(
                f"Method {method} not allowed for websocket path {url_path}. "
                f"Matching methods: {matching_methods}"
            )

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket method not allowed",
                }
            )
            return

        except WebsocketMismatch:
            app.logger.warning(
                f"Websocket request to {url_path} matched a non-websocket route"
            )

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket protocol mismatch",
                }
            )
            return

        except RequestRedirect as exc:
            app.logger.warning(
                f"Websocket path {url_path} requires redirect to {exc.new_url}"
            )

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket route requires redirect",
                }
            )
            return

        req = app.request_class(
            scope,
            receive,
            send,
            app,
            cast(dict, path_kwargs),
            cast(Callable, route_handler),
        )

        try:
            with request_context(
                app=app,
                request=req,
                controller=route_handler.__self__,  # type: ignore
            ) as ctx:
                try:
                    await run_sync_or_async(
                        route_handler,  # type: ignore
                        req,
                        **path_kwargs,
                    )
                finally:
                    await app._close_context_sessions(ctx)

        except Exception as exc:
            await send(
                {
                    "type": "websocket.close",
                    "code": 1011,
                    "reason": "Internal server error",
                }
            )

            app.logger.critical(
                f"Unhandled critical error in websocket: "
                f"({req.method}) {req.path}, "
                f"{req.route_parameters}: {exc}"
            )

            raise

    async def close_context_sessions(self, ctx: Any) -> None:
        """
        Closes database sessions a WebSocket handler opened through the
        request context (Model.query(), repositories). HTTP requests have
        the database middleware for that; sockets do not. Work that was not
        committed explicitly is rolled back by the close.
        """
        app = self._app
        sessions = ctx.sessions
        if sessions is None:
            return
        for session in list(sessions.sessions.values()):
            try:
                await session.close()
            except Exception as exc:  # pragma: no cover - defensive
                app.logger.exception(exc)
        ctx.sessions = None

    def check_socket_handler(self, ctrl: type, handler: Callable) -> None:
        """
        Refuses a WebSocket handler that carries a decorator that only works
        through HTTP middleware: it would be silently ignored, and a socket
        meant to require a login would be open to everyone.
        """
        app = self._app
        for attribute, decorator in app._MIDDLEWARE_DECORATORS.items():
            if getattr(handler, attribute, None) or getattr(ctrl, attribute, None):
                raise ValueError(
                    f"{ctrl.__name__}.{handler.__name__} is a WebSocket handler "
                    f"with {decorator} (on the handler or its controller). HTTP "
                    "middleware does not run for WebSockets, so it would have no "
                    "effect. Check the user or open a session inside the handler, "
                    "and keep sockets in a controller of their own."
                )
