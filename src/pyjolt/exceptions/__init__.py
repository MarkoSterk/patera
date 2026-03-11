"""
Exceptions submodule
"""

from .http_exceptions import (
    BaseHttpException,
    StaticAssetNotFound,
    AborterException,
    abort,
    html_abort,
)

from .runtime_exceptions import (
    CustomException,
    MethodNotControllerMethod,
    UnexpectedDecorator,
)

from .exception_handler import ExceptionHandler, handles
from werkzeug.exceptions import NotFound, MethodNotAllowed

__all__ = [
    "CustomException",
    "BaseHttpException",
    "StaticAssetNotFound",
    "AborterException",
    "abort",
    "html_abort",
    "MethodNotControllerMethod",
    "UnexpectedDecorator",
    "ExceptionHandler",
    "handles",
    "NotFound",
    "MethodNotAllowed",
]
