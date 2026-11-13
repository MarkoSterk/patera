"""
The telemetry middleware: one SERVER span and one duration measurement per
HTTP request.
"""

from __future__ import annotations

import time
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Optional

from loguru import logger
from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.trace import Link, SpanKind, Status, StatusCode
from opentelemetry.trace.span import format_span_id, format_trace_id

from patera import Request, Response
from patera.exceptions.runtime_exceptions import ClientDisconnected
from patera.middleware import MiddlewareBase

from .attributes import (
    captured_headers,
    header_carrier,
    method_attributes,
    request_attributes,
    response_header_pairs,
    span_name,
)

if TYPE_CHECKING:
    from .extension import Telemetry


class TelemetryMiddleware(MiddlewareBase):
    """
    Starts a SERVER span for each HTTP request and ends it when the request
    is finished: the response sent completely, the request failed, or the
    client left. Registered by the ``Telemetry`` extension.

    It is the outermost middleware (order -200) and opts in to requests no
    route matched and to static files, so it can see every request;
    ``TRACE_UNMATCHED``, ``TRACE_STATIC`` and ``EXCLUDE_PATHS`` choose which
    are traced.
    """

    _order_: ClassVar[int] = -200
    _middleware: ClassVar[bool] = True
    run_on_unmatched: ClassVar[bool] = True
    run_on_static: ClassVar[bool] = True
    open_api_spec: ClassVar[bool] = False

    def __init__(self, app: Any, next_app: Callable) -> None:
        super().__init__(app, next_app)
        self._telemetry = self._find_extension()

    def _find_extension(self) -> "Telemetry":
        from .extension import Telemetry

        for extension in self.app.extensions.values():
            if isinstance(extension, Telemetry):
                return extension
        raise RuntimeError(
            "TelemetryMiddleware is registered by the Telemetry extension; "
            "add Telemetry (or a subclass) to app_extensions instead."
        )

    def traces(self, req: Request) -> bool:
        """Whether this request gets a span."""
        config = self._telemetry.configs
        if not config.ENABLED:
            return False
        if not req.route_matched and not config.TRACE_UNMATCHED:
            return False
        if req.static_resource and not config.TRACE_STATIC:
            return False
        path = req.scope.get("path", "")
        return not any(fnmatchcase(path, pattern) for pattern in config.EXCLUDE_PATHS)

    async def middleware(self, req: Request) -> Response:
        if not self.traces(req):
            return await self.next(req)

        route = (
            self.app.router.path_of(req.route_handler) if req.route_matched else None
        )
        request_span = RequestSpan(self._telemetry, req, route)
        req.wrap_send(request_span.watch)
        req.on_finish(request_span.finish)
        try:
            res = await self.next(req)
        except Exception as exc:
            request_span.failed(exc)
            raise
        request_span.handled(req)
        return res


class RequestSpan:
    """The span, metric and log context of one request."""

    def __init__(self, telemetry: "Telemetry", req: Request, route: Optional[str]):
        config = telemetry.configs
        self.config = config
        self.telemetry = telemetry
        self.route = route
        self.method = req.method
        self.scheme = req.scope.get("scheme", "http")
        self.status: Optional[int] = None
        self.error_type: Optional[str] = None
        self.response_headers: list[tuple[str, str]] = []
        self.started = time.perf_counter()

        headers = header_carrier(req.scope)
        incoming = propagate.extract(headers)
        links: list[Link] = []
        if config.TRUST_INCOMING_CONTEXT:
            parent = incoming
        else:
            parent = otel_context.Context()
            caller = trace.get_current_span(incoming).get_span_context()
            if caller.is_valid:
                links.append(Link(caller))

        self.span = telemetry.tracer.start_span(
            span_name(self.method, route),
            context=parent,
            kind=SpanKind.SERVER,
            attributes=request_attributes(req, route, headers, config),
            links=links,
        )
        self._context_token = otel_context.attach(
            trace.set_span_in_context(self.span, parent)
        )
        span_context = self.span.get_span_context()
        self.trace_id = (
            format_trace_id(span_context.trace_id) if span_context.is_valid else None
        )
        self._log_context: Any = None
        if config.LOG_CORRELATION and span_context.is_valid:
            self._log_context = logger.contextualize(
                trace_id=self.trace_id, span_id=format_span_id(span_context.span_id)
            )
            self._log_context.__enter__()
        self._finished = False

    def watch(self, send: Callable) -> Callable:
        """Send wrapper: notes the status, adds the trace id header if asked."""

        async def watching_send(message: dict) -> None:
            if message.get("type") == "http.response.start":
                self.status = message.get("status")
                headers = message.get("headers", [])
                if self.config.CAPTURE_RESPONSE_HEADERS:
                    self.response_headers = response_header_pairs(headers)
                header_name = self.config.TRACE_ID_RESPONSE_HEADER
                if header_name and self.trace_id:
                    message = {
                        **message,
                        "headers": [
                            *headers,
                            (
                                header_name.lower().encode("latin-1"),
                                self.trace_id.encode(),
                            ),
                        ],
                    }
            await send(message)

        return watching_send

    def failed(self, exc: BaseException) -> None:
        """An exception passed through the middleware chain."""
        self.error_type = type(exc).__qualname__
        if self.span.is_recording():
            self.span.record_exception(exc)

    def handled(self, req: Request) -> None:
        """The chain returned: add what is known only now."""
        if not self.span.is_recording():
            return
        if req.route_matched:
            handler = req.route_handler  # JoltUI may have swapped in a component
            name = getattr(handler, "__qualname__", None)
            if name:
                self.span.set_attribute("code.function.name", name)
        if self.config.RECORD_USER_ID:
            user = req.user
            user_id = (
                getattr(user, self.config.USER_ID_ATTRIBUTE, None) if user else None
            )
            if user_id is not None:
                self.span.set_attribute("enduser.id", str(user_id))

    def finish(self, exc: Optional[BaseException]) -> None:
        """Ends the span and records the duration (``req.on_finish``)."""
        if self._finished:
            return
        self._finished = True
        try:
            self._end(exc)
        finally:
            if self._log_context is not None:
                self._log_context.__exit__(None, None, None)
            otel_context.detach(self._context_token)

    def _end(self, exc: Optional[BaseException]) -> None:
        span = self.span
        status = self.status
        disconnected = isinstance(exc, ClientDisconnected)

        error_type: Optional[str] = None
        if status is not None and status >= 500:
            error_type = self.error_type or str(status)
        elif status is None and exc is not None and not disconnected:
            error_type = self.error_type or type(exc).__qualname__
            if span.is_recording() and self.error_type is None:
                span.record_exception(exc)

        if span.is_recording():
            if status is not None:
                span.set_attribute("http.response.status_code", status)
            if disconnected:
                span.add_event("client disconnected")
            if self.response_headers:
                span.set_attributes(
                    captured_headers(
                        "http.response.header",
                        self.response_headers,
                        self.config.CAPTURE_RESPONSE_HEADERS,
                        self.config.REDACT_HEADERS,
                    )
                )
            if error_type is not None:
                span.set_attribute("error.type", error_type)
                span.set_status(Status(StatusCode.ERROR, error_type))
        span.end()

        histogram = self.telemetry.request_duration
        if histogram is not None:
            attributes: dict[str, Any] = {
                **method_attributes(self.method),
                "url.scheme": self.scheme,
            }
            attributes.pop("http.request.method_original", None)
            if self.route:
                attributes["http.route"] = self.route
            if status is not None:
                attributes["http.response.status_code"] = status
            if error_type is not None:
                attributes["error.type"] = error_type
            histogram.record(time.perf_counter() - self.started, attributes)
