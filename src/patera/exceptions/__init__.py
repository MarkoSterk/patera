"""
Exceptions submodule
"""

from .http_exceptions import (
    BaseHttpException,
    StaticAssetNotFound,
    AborterException,
    StaticPageNotFound,
    InvalidRequestBody,
    RequestBodyTooLarge,
    abort,
    html_abort,
)

from .runtime_exceptions import (
    CustomException,
    MethodNotControllerMethod,
    UnexpectedDecorator,
    DuplicateRouteError,
    CircularDependencyError,
)

from .exception_handler import ExceptionHandler, handles, exception_handler
from werkzeug.exceptions import NotFound, MethodNotAllowed

__all__ = [
    "CustomException",
    "BaseHttpException",
    "StaticAssetNotFound",
    "StaticPageNotFound",
    "AborterException",
    "InvalidRequestBody",
    "RequestBodyTooLarge",
    "abort",
    "html_abort",
    "MethodNotControllerMethod",
    "UnexpectedDecorator",
    "DuplicateRouteError",
    "CircularDependencyError",
    "ExceptionHandler",
    "handles",
    "NotFound",
    "MethodNotAllowed",
    "exception_handler",
]
