"""
Collection of http exceptions that can be raised
"""

from typing import Any, Optional
from ..http_statuses import HttpStatus


class BaseHttpException(Exception):
    """
    Base http exception class
    """

    def __init__(
        self,
        message: str = "",
        status_code: int | HttpStatus = 500,
        status="error",
        data=None,
    ):
        """
        Init method
        """
        self.message = message
        if isinstance(status_code, HttpStatus):
            status_code = status_code.value
        self.status_code = status_code
        self.status = status
        self.data = data


class StaticAssetNotFound(BaseHttpException):
    """
    HTTP exception for static assets not found
    """

    def __init__(
        self,
        message: str = "Static asset not found",
        status_code: int = 404,
        status: str = "error",
        data: Any = None,
    ):
        super().__init__(message, status_code, status, data)


class AborterException(BaseHttpException):
    """
    Aborter exception
    """

    def __init__(
        self,
        message: str = "",
        status_code: int = 400,
        status: str = "error",
        data: Optional[Any] = None,
    ):
        super().__init__(message, status_code, status, data)


class HtmlAborterException(BaseHttpException):
    """
    Html aborter exception
    """

    def __init__(
        self, template: str, status_code: int | HttpStatus, data: Optional[Any] = None
    ):
        super().__init__("Error", status_code=status_code, data=data)
        self.template = template
        if isinstance(status_code, HttpStatus):
            status_code = status_code.value
        self.status_code = status_code
        self.data = data


def abort(
    msg: str,
    status_code: int | HttpStatus = HttpStatus.BAD_REQUEST,
    status: str = "error",
    data: Any = None,
):
    """
    Aborts request by raising an aborter exception
    """
    if isinstance(status_code, HttpStatus):
        status_code = status_code.value
    raise AborterException(msg, status_code, status, data)


def html_abort(
    template: str,
    status_code: int | HttpStatus = HttpStatus.BAD_REQUEST,
    data: Any = None,
):
    """
    Aborts request with html response
    """
    if isinstance(status_code, HttpStatus):
        status_code = status_code.value
    raise HtmlAborterException(template, status_code, data)
