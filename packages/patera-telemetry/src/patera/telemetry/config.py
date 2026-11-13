"""
Configuration of the telemetry extension (the ``TELEMETRY`` config block).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_REDACTED_HEADERS: list[str] = [
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
]

INTEGRATIONS: dict[str, str] = {
    "sqlalchemy": "patera-telemetry[sqlalchemy]",
    "httpx": "patera-telemetry[httpx]",
    "redis": "patera-telemetry[redis]",
}


class TelemetryConfig(BaseModel):
    """
    Settings of the ``Telemetry`` extension.

    Options left at None defer to the standard ``OTEL_*`` environment
    variables and then to the OpenTelemetry SDK defaults. Secrets, such as
    the API key of a hosted backend, belong in ``OTEL_EXPORTER_OTLP_HEADERS``
    and are deliberately not settings.
    """

    ENABLED: bool = Field(
        True,
        description="False keeps the extension installed but registers nothing.",
    )
    SERVICE_NAME: Optional[str] = Field(
        None, description="service.name (default: the APP_NAME setting)."
    )
    SERVICE_VERSION: Optional[str] = Field(
        None, description="service.version (default: the VERSION setting)."
    )
    ENVIRONMENT: Optional[str] = Field(
        None,
        description='deployment.environment.name, such as "production".',
    )
    RESOURCE_ATTRIBUTES: dict[str, str] = Field(
        default_factory=dict,
        description="Extra resource attributes added to all telemetry.",
    )

    SETUP_SDK: bool = Field(
        False,
        description=(
            "True: the extension creates the tracer and meter providers and "
            "their exporters at startup and flushes them at shutdown. False: "
            "use the providers configured elsewhere (opentelemetry-instrument, "
            "a vendor distribution); without any, telemetry is a no-op."
        ),
    )
    EXPORTER: Literal["otlp", "console", "none"] = Field(
        "otlp", description="Where SETUP_SDK sends traces and metrics."
    )
    OTLP_ENDPOINT: Optional[str] = Field(
        None,
        description=(
            "Base URL of the OTLP receiver, such as http://localhost:4318. "
            "None: OTEL_EXPORTER_OTLP_ENDPOINT or the SDK default."
        ),
    )
    OTLP_PROTOCOL: Literal["http/protobuf", "grpc"] = Field(
        "http/protobuf",
        description='OTLP transport; "grpc" needs patera-telemetry[grpc].',
    )
    SAMPLE_RATIO: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Share of new traces recorded with SETUP_SDK. Requests that "
            "continue a caller's trace follow the caller's decision."
        ),
    )
    METRICS: bool = Field(
        True, description="Record the http.server.request.duration histogram."
    )
    METRIC_EXPORT_INTERVAL: float = Field(
        60.0, gt=0, description="Seconds between metric exports (SETUP_SDK)."
    )

    EXCLUDE_PATHS: list[str] = Field(
        default_factory=list,
        description='Glob patterns of paths never traced, such as "/health".',
    )
    TRACE_STATIC: bool = Field(False, description="Trace static file requests.")
    TRACE_UNMATCHED: bool = Field(
        True, description="Trace requests no route matched (404, 405, redirects)."
    )
    TRUST_INCOMING_CONTEXT: bool = Field(
        True,
        description=(
            "Continue the trace named by an incoming traceparent header. "
            "False: start a new trace and only link to the caller's, so "
            "clients cannot join your traces or force sampling."
        ),
    )

    RECORD_CLIENT_ADDRESS: bool = Field(
        False, description="Record the client IP address (personal data)."
    )
    RECORD_QUERY: bool = Field(
        False, description="Record the query string (may hold tokens or personal data)."
    )
    CAPTURE_REQUEST_HEADERS: list[str] = Field(
        default_factory=list, description="Request header names to record."
    )
    CAPTURE_RESPONSE_HEADERS: list[str] = Field(
        default_factory=list, description="Response header names to record."
    )
    REDACT_HEADERS: list[str] = Field(
        default_factory=lambda: list(DEFAULT_REDACTED_HEADERS),
        description="Captured headers whose values are replaced by [REDACTED].",
    )
    RECORD_USER_ID: bool = Field(
        False, description="Record the authenticated user's id as enduser.id."
    )
    USER_ID_ATTRIBUTE: str = Field(
        "id", description="Attribute of req.user recorded as enduser.id."
    )

    LOG_CORRELATION: bool = Field(
        True,
        description="Add trace_id and span_id to the log records of a request.",
    )
    INSTRUMENT: list[Literal["sqlalchemy", "httpx", "redis"]] = Field(
        default_factory=list,
        description="Libraries to instrument; each needs its extra installed.",
    )
    TRACE_ID_RESPONSE_HEADER: Optional[str] = Field(
        None,
        description=(
            'Response header that returns the trace id, such as "X-Trace-Id". '
            "The only setting that changes responses."
        ),
    )
