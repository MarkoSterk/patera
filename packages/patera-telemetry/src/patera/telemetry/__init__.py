"""
OpenTelemetry for Patera: request tracing, the request-duration metric, log
correlation and library instrumentation.
"""

from .background import run_traced_in_background
from .config import TelemetryConfig
from .extension import Telemetry
from .middleware import TelemetryMiddleware

__all__ = [
    "Telemetry",
    "TelemetryConfig",
    "TelemetryMiddleware",
    "run_traced_in_background",
]
