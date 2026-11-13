"""
Creating and shutting down the OpenTelemetry SDK providers (SETUP_SDK).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from opentelemetry import metrics, trace

if TYPE_CHECKING:
    from loguru import Logger

    from .config import TelemetryConfig

SDK_EXTRA = 'SETUP_SDK needs the OpenTelemetry SDK: pip install "patera-telemetry[sdk]"'
GRPC_EXTRA = (
    'OTLP_PROTOCOL = "grpc" needs the gRPC exporter: '
    'pip install "patera-telemetry[grpc]"'
)


def _signal_endpoint(base: Optional[str], signal: str, protocol: str) -> Optional[str]:
    """The exporter endpoint for one signal; None lets the exporter decide."""
    if base is None:
        return None
    if protocol == "grpc":
        return base
    return f"{base.rstrip('/')}/v1/{signal}"


def _span_exporter(config: "TelemetryConfig") -> Any:
    if config.EXPORTER == "none":
        return None
    if config.EXPORTER == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()
    endpoint = _signal_endpoint(config.OTLP_ENDPOINT, "traces", config.OTLP_PROTOCOL)
    if config.OTLP_PROTOCOL == "grpc":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError as exc:
            raise RuntimeError(GRPC_EXTRA) from exc
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    return OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()


def _metric_exporter(config: "TelemetryConfig") -> Any:
    if config.EXPORTER == "none":
        return None
    if config.EXPORTER == "console":
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

        return ConsoleMetricExporter()
    endpoint = _signal_endpoint(config.OTLP_ENDPOINT, "metrics", config.OTLP_PROTOCOL)
    if config.OTLP_PROTOCOL == "grpc":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
        except ImportError as exc:
            raise RuntimeError(GRPC_EXTRA) from exc
    else:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
    return OTLPMetricExporter(endpoint=endpoint) if endpoint else OTLPMetricExporter()


def resource_attributes(
    config: "TelemetryConfig", service_name: str, service_version: str
) -> dict[str, str]:
    attributes = {"service.name": service_name, "service.version": service_version}
    if config.ENVIRONMENT:
        attributes["deployment.environment.name"] = config.ENVIRONMENT
    attributes.update(config.RESOURCE_ATTRIBUTES)
    return attributes


def setup_sdk(
    config: "TelemetryConfig",
    service_name: str,
    service_version: str,
    logger: "Logger",
) -> tuple[Any, Any]:
    """
    Creates the tracer and meter providers and makes them the global ones.

    OpenTelemetry allows the global providers to be set once per process. A
    provider that is already set (by opentelemetry-instrument, a vendor
    distribution, or an earlier startup) is kept, the new one is shut down,
    and a warning is logged. Returns the providers that were installed, or
    None for each that was not.
    """
    try:
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError as exc:
        raise RuntimeError(SDK_EXTRA) from exc

    resource = Resource.create(
        resource_attributes(config, service_name, service_version)
    )

    new_tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(config.SAMPLE_RATIO)),
    )
    span_exporter = _span_exporter(config)
    if span_exporter is not None:
        new_tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(new_tracer_provider)
    tracer_provider: Optional[Any] = new_tracer_provider
    if trace.get_tracer_provider() is not new_tracer_provider:
        logger.warning(
            "Telemetry: a tracer provider is already configured; SETUP_SDK keeps it."
        )
        new_tracer_provider.shutdown()
        tracer_provider = None

    meter_provider: Optional[Any] = None
    if config.METRICS:
        metric_exporter = _metric_exporter(config)
        readers = (
            [
                PeriodicExportingMetricReader(
                    metric_exporter,
                    export_interval_millis=config.METRIC_EXPORT_INTERVAL * 1000,
                )
            ]
            if metric_exporter is not None
            else []
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        metrics.set_meter_provider(meter_provider)
        if metrics.get_meter_provider() is not meter_provider:
            logger.warning(
                "Telemetry: a meter provider is already configured; SETUP_SDK keeps it."
            )
            meter_provider.shutdown()
            meter_provider = None

    return tracer_provider, meter_provider


def shutdown_sdk(providers: tuple[Any, Any], logger: "Logger") -> None:
    """Flushes and shuts down the providers setup_sdk installed."""
    for provider in providers:
        if provider is None:
            continue
        try:
            provider.force_flush()
            provider.shutdown()
        except Exception as exc:  # shutdown must not fail the application's
            logger.error(f"Telemetry: shutting down {provider!r} failed: {exc}")
