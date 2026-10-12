from typing import Any
from patera import HttpStatus
from patera.exceptions import BaseHttpException


class AuthenticationException(BaseHttpException):
    """
    Authentication exception for endpoints which require authentication.
    The client is not (validly) logged in -> 401 Unauthorized.
    """

    def __init__(self, message: str):
        super().__init__(message, HttpStatus.UNAUTHORIZED, "error", None)


class AuthorizationException(BaseHttpException):
    """
    Authorization exception for endpoints which require specific roles.
    The client is logged in but lacks a required role -> 403 Forbidden.
    """

    def __init__(self, message: str, roles: list[Any]):
        super().__init__(message, HttpStatus.FORBIDDEN, "error", roles)
