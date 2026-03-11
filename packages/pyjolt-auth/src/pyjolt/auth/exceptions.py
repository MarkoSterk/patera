from typing import Any
from pyjolt import HttpStatus
from pyjolt.exceptions import BaseHttpException


class AuthenticationException(BaseHttpException):
    """
    Authentication exception for endpoints which require authentication
    """

    def __init__(self, message: str):
        super().__init__(message, HttpStatus.FORBIDDEN, "error", None)


class AuthorizationException(BaseHttpException):
    """
    Authorization exception for endpoints which require specific roles
    """

    def __init__(self, message: str, roles: list[Any]):
        super().__init__(message, HttpStatus.UNAUTHORIZED, "error", roles)


class InvalidJWTError(BaseHttpException):
    """
    Invalid or expired JWT token error
    """

    def __init__(self, message: str):
        super().__init__(message, 401, "error", None)
