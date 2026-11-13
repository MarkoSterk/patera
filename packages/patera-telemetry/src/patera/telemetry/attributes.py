"""
Span and metric attributes for HTTP server requests, following the
OpenTelemetry semantic conventions for HTTP (stable).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Optional

if TYPE_CHECKING:
    from patera import Request

    from .config import TelemetryConfig

KNOWN_METHODS: frozenset[str] = frozenset(
    {"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)

DURATION_BUCKETS: list[float] = [
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
]

REDACTED = "[REDACTED]"


def header_carrier(scope: dict[str, Any]) -> dict[str, str]:
    """
    The request headers as a dict of lower-case names, the shape the
    OpenTelemetry propagators read. Repeated headers are joined with ", ".
    """
    carrier: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        name = raw_name.decode("latin-1").lower()
        value = raw_value.decode("latin-1")
        carrier[name] = f"{carrier[name]}, {value}" if name in carrier else value
    return carrier


def method_attributes(method: str) -> dict[str, str]:
    """http.request.method, with http.request.method_original for others."""
    if method in KNOWN_METHODS:
        return {"http.request.method": method}
    return {"http.request.method": "_OTHER", "http.request.method_original": method}


def span_name(method: str, route: Optional[str]) -> str:
    """'{method} {route}', or the method alone when no route matched."""
    name = method if method in KNOWN_METHODS else "HTTP"
    return f"{name} {route}" if route else name


def _server_address(
    scope: dict[str, Any], headers: dict[str, str]
) -> tuple[Optional[str], Optional[int]]:
    host = headers.get("host")
    if host:
        if host.startswith("["):  # [IPv6]:port
            address, _, rest = host[1:].partition("]")
            port = rest[1:] if rest.startswith(":") else ""
        else:
            address, _, port = host.partition(":")
        return address, int(port) if port.isdigit() else None
    server = scope.get("server")
    if server:
        return str(server[0]), int(server[1]) if server[1] is not None else None
    return None, None


def request_attributes(
    req: "Request",
    route: Optional[str],
    headers: dict[str, str],
    config: "TelemetryConfig",
) -> dict[str, Any]:
    """The attributes a server span starts with."""
    scope = req.scope
    attributes: dict[str, Any] = {
        **method_attributes(req.method),
        "url.scheme": scope.get("scheme", "http"),
        "url.path": scope.get("path", ""),
    }
    if route:
        attributes["http.route"] = route
    address, port = _server_address(scope, headers)
    if address:
        attributes["server.address"] = address
    if port is not None:
        attributes["server.port"] = port
    if scope.get("http_version"):
        attributes["network.protocol.version"] = scope["http_version"]
    if "user-agent" in headers:
        attributes["user_agent.original"] = headers["user-agent"]
    if config.RECORD_CLIENT_ADDRESS and scope.get("client"):
        attributes["client.address"] = str(scope["client"][0])
    if config.RECORD_QUERY and scope.get("query_string"):
        attributes["url.query"] = scope["query_string"].decode("latin-1")
    attributes.update(
        captured_headers(
            "http.request.header",
            ((name, value) for name, value in headers.items()),
            config.CAPTURE_REQUEST_HEADERS,
            config.REDACT_HEADERS,
        )
    )
    return attributes


def captured_headers(
    prefix: str,
    headers: Iterable[tuple[str, str]],
    capture: list[str],
    redact: list[str],
) -> dict[str, list[str]]:
    """
    ``{prefix}.{name}`` attributes for the headers named in ``capture``,
    each a list of values. Values of headers named in ``redact`` are
    replaced by "[REDACTED]".
    """
    wanted = {name.lower() for name in capture}
    if not wanted:
        return {}
    hidden = {name.lower() for name in redact}
    captured: dict[str, list[str]] = {}
    for name, value in headers:
        name = name.lower()
        if name not in wanted:
            continue
        key = (
            f"{prefix}.{name}"  # lower case, hyphens kept, as the conventions name them
        )
        captured.setdefault(key, []).append(REDACTED if name in hidden else value)
    return captured


def response_header_pairs(
    raw_headers: Iterable[tuple[bytes, bytes]],
) -> list[tuple[str, str]]:
    """ASGI response headers as (name, value) strings."""
    return [
        (name.decode("latin-1"), value.decode("latin-1")) for name, value in raw_headers
    ]
