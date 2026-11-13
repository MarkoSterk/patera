"""
The Telemetry extension: OpenTelemetry tracing, metrics and log correlation.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Generic, Optional, TypeVar

from opentelemetry import metrics, trace

from patera import BaseExtension, MiddlewareBase, Request

from . import integrations, sdk
from .attributes import DURATION_BUCKETS
from .config import TelemetryConfig

AppT = TypeVar("AppT", bound=Any)

try:
    __version__ = version("patera-telemetry")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

INSTRUMENTATION_NAME = "patera.telemetry"


def _require_core_support() -> None:
    """The middleware needs the request pipeline of recent Patera cores."""
    missing = [
        name
        for owner, name in (
            (Request, "on_finish"),
            (Request, "wrap_send"),
            (MiddlewareBase, "run_on_unmatched"),
        )
        if not hasattr(owner, name)
    ]
    if missing:
        raise RuntimeError(
            "patera-telemetry needs a newer patera core (missing: "
            + ", ".join(missing)
            + "). Upgrade patera."
        )


class Telemetry(BaseExtension[AppT, TelemetryConfig], Generic[AppT]):
    """
    OpenTelemetry for a Patera application.

    Registers ``TelemetryMiddleware``, which records a SERVER span and the
    ``http.server.request.duration`` metric for each HTTP request, adds
    ``trace_id`` and ``span_id`` to the request's log records, and
    instruments the libraries named in ``INSTRUMENT``.

    With ``SETUP_SDK`` the extension also creates the tracer and meter
    providers at startup, so each server worker gets its own, and flushes
    them at shutdown. Otherwise it uses the providers configured elsewhere;
    without any, every OpenTelemetry call is a no-op.

    Configured by the ``TELEMETRY`` setting (``TelemetryConfig``).
    """

    def init(self) -> None:
        _require_core_support()
        self._providers: tuple[Any, Any] = (None, None)
        self._sdk_started = False
        self._tracer: Optional[trace.Tracer] = None
        self._request_duration: Optional[metrics.Histogram] = None
        config = self.configs
        if not config.ENABLED:
            return

        from .middleware import TelemetryMiddleware

        self.app.register_middleware(TelemetryMiddleware)
        integrations.instrument(list(config.INSTRUMENT))
        if config.SETUP_SDK:
            self.app.add_on_startup_method(self.start_sdk)
            self.app.add_on_shutdown_method(self.stop_sdk)

    @property
    def service_name(self) -> str:
        return self.configs.SERVICE_NAME or self.app.app_name

    @property
    def service_version(self) -> str:
        return self.configs.SERVICE_VERSION or self.app.version

    @property
    def tracer(self) -> trace.Tracer:
        """The tracer of the global provider (resolved when it is set)."""
        if self._tracer is None:
            self._tracer = trace.get_tracer(INSTRUMENTATION_NAME, __version__)
        return self._tracer

    @property
    def request_duration(self) -> Optional[metrics.Histogram]:
        """The http.server.request.duration histogram (None if METRICS is off)."""
        if not self.configs.METRICS:
            return None
        if self._request_duration is None:
            meter = metrics.get_meter(INSTRUMENTATION_NAME, __version__)
            self._request_duration = meter.create_histogram(
                "http.server.request.duration",
                unit="s",
                description="Duration of HTTP server requests.",
                explicit_bucket_boundaries_advisory=DURATION_BUCKETS,
            )
        return self._request_duration

    def start_sdk(self) -> None:
        """Startup action with SETUP_SDK: creates and installs the providers."""
        if self._sdk_started:
            return
        self._sdk_started = True
        self._providers = sdk.setup_sdk(
            self.configs, self.service_name, self.service_version, self.app.logger
        )
        self.app.logger.info(
            f"Telemetry: exporting with {self.configs.EXPORTER} as "
            f"{self.service_name} {self.service_version}"
        )

    def stop_sdk(self) -> None:
        """Shutdown action with SETUP_SDK: flushes and shuts down the providers."""
        sdk.shutdown_sdk(self._providers, self.app.logger)
        self._providers = (None, None)
