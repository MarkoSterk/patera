"""
Collection of http exceptions that can be raised
"""

from typing import Any, Optional

from pydantic import ValidationError

from ..http_statuses import HttpStatus


class BaseHttpException(Exception):
    """
    Base http exception class
    """

    def __init__(
        self,
        message: str = "",
        status_code: int | HttpStatus = HttpStatus.INTERNAL_SERVER_ERROR,
        status="error",
        data=None,
    ):
        """
        Init method
        """
        super().__init__(message)
        self.message = message
        if isinstance(status_code, HttpStatus):
            status_code = status_code.value
        self.status_code = status_code
        self.status = status
        self.data = data


class StaticPageNotFound(BaseHttpException):
    """
    Static page not found error
    """

    def __init__(
        self,
        page: str,
        status_code: int = HttpStatus.NOT_FOUND,
        status: str = "error",
        data: Any = None,
    ):
        super().__init__(f"Static page {page} not found", status_code, status, data)


class StaticAssetNotFound(BaseHttpException):
    """
    HTTP exception for static assets not found
    """

    def __init__(
        self,
        message: str = "Static asset not found",
        status_code: int = HttpStatus.NOT_FOUND,
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
        status_code: int = HttpStatus.BAD_REQUEST,
        status: str = "error",
        data: Optional[Any] = None,
    ):
        super().__init__(message, status_code, status, data)


class InvalidRequestBody(BaseHttpException):
    """
    Raised when a request body cannot be parsed, such as malformed JSON.
    Answered with 400 Bad Request.
    """

    def __init__(
        self,
        message: str = "Malformed request body",
        status_code: int = HttpStatus.BAD_REQUEST,
        status: str = "error",
        data: Any = None,
    ):
        super().__init__(message, status_code, status, data)


class RequestBodyTooLarge(BaseHttpException):
    """
    Raised when a request body is larger than the allowed maximum.
    Answered with 413 Content Too Large.
    """

    def __init__(
        self,
        max_content_length: int,
        message: str = "Request body too large",
        status_code: int = HttpStatus.PAYLOAD_TOO_LARGE,
        status: str = "error",
    ):
        super().__init__(
            message, status_code, status, {"max_content_length": max_content_length}
        )
        self.max_content_length = max_content_length


class RequestValidationError(BaseHttpException):
    """
    Raised when @consumes cannot build the declared model from the request
    body. Answered with 422 Unprocessable Content; ``data`` (and ``errors``)
    lists each problem's location, message and type. The submitted values are
    left out, so a rejected password is never sent back.

    The original Pydantic error is ``validation_error``. A ValidationError
    raised anywhere else (in handler code, or validating data from a database
    or another service) is a server error, answered with 500.
    """

    def __init__(
        self,
        validation_error: ValidationError,
        message: str = "Validation failed",
        status_code: int = HttpStatus.UNPROCESSABLE_ENTITY,
        status: str = "error",
    ):
        errors = validation_error.errors(
            include_url=False, include_input=False, include_context=False
        )
        super().__init__(message, status_code, status, errors)
        self.validation_error = validation_error
        self.errors: list[Any] = list(errors)


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
    raise AborterException(msg, status_code, status, data)


def html_abort(
    template: str,
    status_code: int | HttpStatus = HttpStatus.BAD_REQUEST,
    data: Any = None,
):
    """
    Aborts request with html response
    """
    raise HtmlAborterException(template, status_code, data)
