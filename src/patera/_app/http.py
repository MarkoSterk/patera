"""
HTTP request handling: routing, routing-error responses, the middleware
chain entry point, request observers and request/response logging.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import (
    Any,
    Callable,
    Optional,
    Type,
    cast,
)
from werkzeug.exceptions import NotFound, MethodNotAllowed
from werkzeug.routing import WebsocketMismatch, RequestRedirect


from ..http_methods import HttpMethod
from ..http_statuses import HttpStatus
from ..serializers import json_bytes
from ..request import Request
from ..response import Response
from ..utilities import (
    _extract_response_type,
)
from ..ctx import request_context
from ..exceptions.runtime_exceptions import ClientDisconnected
from ..request_record import RequestObserver, RequestRecord

from ._base import AppPart


def without_body(send: Callable) -> Callable:
    """
    Wraps an ASGI send channel so response bodies are sent empty, for the
    answer to a HEAD request. The start message, with its Content-Length,
    is left as it is: a HEAD response carries the headers of the GET
    response.
    """

    async def head_send(message: dict) -> None:
        if message.get("type") == "http.response.body" and message.get("body"):
            message = {**message, "body": b""}
        await send(message)

    return head_send


@dataclass(frozen=True)
class RoutingOutcome:
    """
    Why no route matched a request, and what the response will be.

    Routing errors are not answered on the spot: the request goes through
    the middleware chain like any other, and the innermost step sends the
    response this outcome describes. Only middleware with
    ``run_on_unmatched = True`` runs for such a request.
    """

    #: "not_found", "method_not_allowed", "protocol_mismatch" or "redirect"
    kind: str
    status: int
    #: Methods the path allows (405 only), sorted.
    allowed_methods: tuple[str, ...] = ()
    #: Where a redirect points (redirects only).
    location: str = ""


def redirect_location(new_url: str, scope: dict) -> str:
    """
    The Location of a trailing-slash redirect: the corrected path and the
    request's query string, without scheme and host.

    The router is bound without a server name, so Werkzeug's ``new_url`` has
    an empty host (``http:///items/``) and no query string. A client resolves
    a path-only Location against the URL it requested, so the redirect also
    keeps the host and scheme a proxy in front of the application uses.
    """
    location = urlsplit(new_url).path
    query_string: bytes = scope.get("query_string", b"")
    if query_string:
        location += "?" + query_string.decode("latin-1")
    return location


class HttpDispatcher(AppPart):
    """
    HTTP request handling: routing, routing-error responses, the middleware
    chain entry point, request observers and request/response logging.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    async def base_app(self, req: Request) -> Response:
        """
        The bare-bones application without any middleware.
        Calls the route handler directly.
        """
        app = self._app
        if req.routing_outcome is not None:
            return await self.send_routing_outcome(req)

        if req.automatic_options is not None:
            return req.res.no_content().set_header(
                "allow", ", ".join(req.automatic_options)
            )

        if req.response.expected_body_type() is None:
            expected = _extract_response_type(req.route_handler)
            req.response._set_expected_body_type(expected)

        res: Response = await req.route_handler.__self__(req.route_handler, req)  # type: ignore

        if isinstance(res, Response):
            app.response_renderer.materialize_body(
                res, req.response.expected_body_type()
            )

        return res

    async def send_routing_outcome(self, req: Request) -> Response:
        """
        Sends the response for a request no route matched, with the
        application's ``abort_*`` and ``redirect_request`` methods, and
        returns the request's response carrying that status code.

        The response is already sent when this returns: middleware sees
        ``req.response_started`` set, and the dispatcher sends nothing more.
        The answer to a HEAD request keeps its headers but has no body.
        """
        app = self._app
        outcome = cast(RoutingOutcome, req.routing_outcome)
        send: Callable = req.send
        if req.method == HttpMethod.HEAD.value:
            send = without_body(send)

        if outcome.kind == "not_found":
            await app.abort_route_not_found(send)
        elif outcome.kind == "method_not_allowed":
            await app.abort_method_not_allowed(send, list(outcome.allowed_methods))
        elif outcome.kind == "protocol_mismatch":
            await app.abort_bad_request(send)
        else:
            await app.redirect_request(send, outcome.location, outcome.status)
        return req.res.status(outcome.status)

    async def send_error(
        self,
        send,
        status_code: int,
        message: str,
        data: Any = None,
        headers: Optional[list[tuple[bytes, bytes]]] = None,
    ) -> None:
        """
        Sends a JSON error response straight to the ASGI ``send`` channel.

        Used for errors raised before a request object exists (routing
        failures). The body has the same shape as every other framework
        error: ``status``, ``message`` and, when there is more to say,
        ``data``. It is encoded like every other JSON response: compact
        UTF-8, with the charset in the content type.
        """
        payload: dict[str, Any] = {"status": "error", "message": message}
        if data is not None:
            payload["data"] = data
        body = json_bytes(payload)
        await send(
            {
                "type": "http.response.start",
                "status": int(status_code),
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    *(headers or []),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def abort_route_not_found(self, send):
        """
        Aborts request because route was not found.
        """
        app = self._app
        await app._send_error(send, HttpStatus.NOT_FOUND, "Endpoint not found")

    async def abort_method_not_allowed(
        self,
        send,
        allowed_methods: list[str],
    ):
        """
        Aborts request because method is not allowed.
        """
        app = self._app
        await app._send_error(
            send,
            HttpStatus.METHOD_NOT_ALLOWED,
            "Method not allowed",
            data={"allowed_methods": allowed_methods},
            headers=[(b"allow", ", ".join(allowed_methods).encode("latin-1"))],
        )

    async def abort_bad_request(self, send) -> None:
        """
        Send a 400 Bad Request response.
        """
        app = self._app
        await app._send_error(send, HttpStatus.BAD_REQUEST, "Bad request")

    async def redirect_request(
        self,
        send,
        location: str,
        status_code: int,
    ) -> None:
        """
        Send an HTTP redirect response.
        """
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"location", location.encode("latin-1")),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"",
            }
        )

    def add_request_observer(self, observer: RequestObserver) -> None:
        """
        Calls ``observer(record)`` with a ``RequestRecord`` after every HTTP
        request, including those answered by the router (404, 405), static
        resources and failed requests. Observers run in the request's task
        once its response has been sent, so they must be quick and must not
        block; an observer that raises is logged and skipped.
        """
        app = self._app
        app._request_observers.append(observer)

    async def handle_http_request(self, scope, receive, send):
        """
        Handles HTTP requests, and reports each one to the request observers.
        """
        app = self._app
        if not app._request_observers:
            return await app._dispatch_http_request(scope, receive, send)

        started_at = time.time()
        start = time.perf_counter()
        status: list[int] = []

        async def observed_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                status.append(message["status"])
            await send(message)

        failed = False
        try:
            return await app._dispatch_http_request(scope, receive, observed_send)
        except BaseException:
            failed = True
            raise
        finally:
            app._notify_request_observers(
                RequestRecord(
                    method=scope["method"].upper(),
                    path=scope["path"],
                    route=scope.get("patera.route"),
                    status_code=status[0]
                    if status
                    else (HttpStatus.INTERNAL_SERVER_ERROR if failed else None),
                    started_at=started_at,
                    duration=time.perf_counter() - start,
                )
            )

    def notify_request_observers(self, record: RequestRecord) -> None:
        app = self._app
        for observer in app._request_observers:
            try:
                observer(record)
            except Exception as exc:  # an observer must not break requests
                app.logger.error(f"Request observer {observer!r} failed: {exc}")

    async def dispatch_http_request(self, scope, receive, send):
        """
        Routes an HTTP request and sends its response.
        """
        app = self._app
        method: str = scope["method"].upper()
        url_path: str = scope["path"]

        app._log_request(scope, method, url_path)

        route_handler: Optional[Callable] = None
        path_kwargs: Mapping[str, Any] = {}
        automatic_options: Optional[list[str]] = None
        # Set when no route matched; answered inside the middleware chain.
        outcome: Optional[RoutingOutcome] = None

        try:
            route_handler, path_kwargs = app.router.match(
                url_path,
                method,
            )
        except NotFound:
            app.logger.info(f"Path {url_path} does not exist")
            outcome = RoutingOutcome("not_found", HttpStatus.NOT_FOUND)
        except MethodNotAllowed as exc:
            matching_methods = sorted(exc.valid_methods or [])

            if method == "OPTIONS" and matching_methods:
                route_handler, path_kwargs, automatic_options = (
                    app._match_automatic_options(scope, url_path, matching_methods)
                )
            else:
                app.logger.warning(
                    f"Method {method} not allowed for path {url_path}. "
                    f"Matching methods: {matching_methods}"
                )
                outcome = RoutingOutcome(
                    "method_not_allowed",
                    HttpStatus.METHOD_NOT_ALLOWED,
                    tuple(matching_methods),
                )
        except WebsocketMismatch:
            app.logger.warning(
                f"Protocol mismatch for path {url_path}: "
                f"HTTP request matched a WebSocket route"
            )
            outcome = RoutingOutcome("protocol_mismatch", HttpStatus.BAD_REQUEST)

        except RequestRedirect as exc:
            location = redirect_location(exc.new_url, scope)
            app.logger.debug(f"Redirecting path {url_path} to {location}")
            outcome = RoutingOutcome(
                "redirect",
                int(exc.code),  # type: ignore[arg-type]
                location=location,
            )

        if app._request_observers and outcome is None:
            scope["patera.route"] = app.router.path_of(cast(Callable, route_handler))

        req = app.request_class(
            scope,
            receive,
            send,
            app,
            cast(dict, path_kwargs),
            cast(Callable, route_handler),
        )
        req.automatic_options = automatic_options
        req.routing_outcome = outcome
        req.route_matched = outcome is None
        req.static_resource = outcome is None and bool(
            getattr(route_handler.__self__, "_static_resource", False)  # type: ignore
            or getattr(route_handler, "_static_resource", False)
        )

        # A client disconnect is answered by nobody, but it still ends the
        # request: finish callbacks learn about it through the exception.
        escaped: Optional[BaseException] = None
        try:
            try:
                with request_context(
                    app=app,
                    request=req,
                    controller=(
                        route_handler.__self__  # type: ignore
                        if outcome is None
                        else None
                    ),
                ):
                    try:
                        res: Response = await app._app(req)

                        if outcome is not None and req.response_started:
                            # The routing error was sent in the innermost step.
                            return None

                        if req.static_resource:
                            return await app.send_response(res, req.send)

                        if not isinstance(res, Response):
                            raise TypeError(
                                "Return object of request handlers must be an instance "
                                f"of Response, got {type(res).__name__}"
                            )

                        response_type: Optional[Type[Any]] = (
                            req.response.expected_body_type()
                        )

                        return await app.send_response(res, req.send, response_type)

                    except Exception as exc:
                        if req.response_started or isinstance(exc, ClientDisconnected):
                            raise
                        return await app._send_exception_response(req, exc)

            except Exception as exc:
                if isinstance(exc, ClientDisconnected):
                    app.logger.info(f"({req.method}) {req.path}: {exc}")
                    escaped = exc
                    return

                if req.response_started:
                    app.logger.error(
                        f"Error after the response started: ({req.method}) {req.path}. "
                        "The connection is closed."
                    )
                    app.logger.exception(exc)
                    raise

                req.res.reset()

                if not app.configs.DEBUG:
                    res = req.res.json(
                        {
                            "status": "error",
                            "message": "Internal server error",
                        }
                    ).status(HttpStatus.INTERNAL_SERVER_ERROR)

                    app.logger.critical(
                        f"Unhandled critical error: ({req.method}) {req.path}, "
                        f"{req.route_parameters}"
                    )
                    app.logger.exception(exc)

                    return await app.send_response(res, req.send, None)

                raise
        except BaseException as exc:
            escaped = exc
            raise
        finally:
            self.run_finish_callbacks(req, escaped)

    def run_finish_callbacks(self, req: Request, exc: Optional[BaseException]) -> None:
        """Runs the callbacks registered with ``req.on_finish``."""
        app = self._app
        for callback in req._finish_callbacks:
            try:
                callback(exc)
            except Exception as error:  # a callback must not break the request
                app.logger.error(
                    f"Request finish callback {callback!r} failed: {error}"
                )

    def match_automatic_options(
        self,
        scope: dict,
        url_path: str,
        allowed_methods: list[str],
    ) -> tuple[Callable, Any, list[str]]:
        """
        Resolves the route handler used to answer an OPTIONS request for a
        route without an explicit OPTIONS handler.
        """
        app = self._app
        requested_method: str = ""
        for key, value in scope.get("headers", []):
            if key.lower() == b"access-control-request-method":
                requested_method = value.decode("latin-1").strip().upper()
                break

        match_method = (
            requested_method
            if requested_method in allowed_methods
            else allowed_methods[0]
        )
        route_handler, path_kwargs = app.router.match(url_path, match_method)
        allow = sorted({*allowed_methods, "OPTIONS"})
        return cast(Callable, route_handler), path_kwargs, allow

    def log_request(self, scope, method: str, url_path: str) -> None:
        """
        Logs incoming request.
        """
        app = self._app
        app.logger.info(
            "HTTP request. "
            f"CLIENT: {(scope.get('client') or ('-', ''))[0]}, "
            f"SCHEME: {scope['scheme']}, "
            f"METHOD: {method}, "
            f"PATH: {url_path}, "
            f"QUERY_STRING: {scope['query_string'].decode('utf-8', 'replace')}"
        )

    def log_response(self, req: Request, status_code: int) -> None:
        """
        Logs outgoing response.
        """
        app = self._app
        app.logger.info(
            "HTTP response. "
            f"CLIENT: {(req.scope.get('client') or ('-', ''))[0]}, "
            f"SCHEME: {req.scope['scheme']}, "
            f"METHOD: {req.method}, "
            f"PATH: {req.path}, "
            f"STATUS_CODE: {status_code}"
        )
