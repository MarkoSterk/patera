"""
Init file for Patera package
"""

# Patera's optional extensions (patera.auth, patera.database, ...) are shipped as
# separate distributions that install into the ``patera`` namespace. Extending
# ``__path__`` makes them importable alongside this regular package, including
# editable/workspace installs where every distribution lives in its own ``src``.
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .patera import Patera, app, on_shutdown, on_startup  # noqa: E402
from .base_extension import BaseExtension  # noqa: E402
from .middleware import MiddlewareBase  # noqa: E402
from .exceptions import abort, html_abort  # noqa: E402
from .configuration_base import BaseConfig  # noqa: E402

from .request import Request, UploadedFile  # noqa: E402
from .response import Response  # noqa: E402

from .utilities import run_sync_or_async, run_in_background, development, ignore  # noqa: E402
from .media_types import MediaType  # noqa: E402
from .http_methods import HttpMethod  # noqa: E402
from .http_statuses import HttpStatus  # noqa: E402
from .logging.logger_config_base import LogLevel  # noqa: E402

# Semantic for Service class
Service = BaseExtension

__all__ = [
    "Patera",
    "abort",
    "Request",
    "Response",
    "run_sync_or_async",
    "run_in_background",
    "UploadedFile",
    "MediaType",
    "HttpMethod",
    "HttpStatus",
    "html_abort",
    "app",
    "on_shutdown",
    "on_startup",
    "BaseExtension",
    "BaseConfig",
    "LogLevel",
    "MiddlewareBase",
    "development",
    "ignore",
    "Service",
]
