"""
Declarative interfaces for external HTTP APIs.
"""

from .api_interface import (
    AuthType,
    service,
    method,
    resource,
    consumes,
    produces,
    headers,
    timeout,
    auth,
    no_auth,
    forward_request,
    MissingApiInterfaceConfigurations,
    ApiInterfaceResponseError,
    ApiInterface,
)

__all__ = [
    "AuthType",
    "service",
    "method",
    "resource",
    "consumes",
    "produces",
    "headers",
    "timeout",
    "auth",
    "no_auth",
    "forward_request",
    "MissingApiInterfaceConfigurations",
    "ApiInterfaceResponseError",
    "ApiInterface",
]
