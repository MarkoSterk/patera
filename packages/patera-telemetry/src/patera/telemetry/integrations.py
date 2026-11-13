"""
Instrumenting libraries with the OpenTelemetry contrib instrumentations.
"""

from __future__ import annotations

import importlib

from .config import INTEGRATIONS

INSTRUMENTORS: dict[str, tuple[str, str]] = {
    "sqlalchemy": (
        "opentelemetry.instrumentation.sqlalchemy",
        "SQLAlchemyInstrumentor",
    ),
    "httpx": ("opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor"),
    "redis": ("opentelemetry.instrumentation.redis", "RedisInstrumentor"),
}


def instrument(names: list[str]) -> None:
    """
    Instruments the named libraries for the whole process. Instrumentation
    patches the libraries, so it applies to every engine or client created
    afterwards, not only Patera's. A library that is already instrumented is
    left as it is.
    """
    for name in names:
        module_name, class_name = INSTRUMENTORS[name]
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise RuntimeError(
                f'Telemetry INSTRUMENT "{name}" needs: pip install "{INTEGRATIONS[name]}"'
            ) from exc
        instrumentor = getattr(module, class_name)()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()
