"""
Exception handler for application
"""

from typing import Any
from pyjolt import Request, Response, HttpStatus
from pyjolt.exceptions import ExceptionHandler, handles
from pydantic import BaseModel, ValidationError


class ErrorResponse(BaseModel):
    message: str
    status: str = "error"
    details: Any | None = None


class Handler(ExceptionHandler):
    @handles(ValidationError)
    async def validation_error_handler(
        self, req: Request, exc: ValidationError
    ) -> Response[ErrorResponse]:
        """Handles validation errors"""
        # Parses validation error details
        details = {}
        if hasattr(exc, "errors"):
            for error in exc.errors():
                details[error["loc"][0]] = error["msg"]

        return req.response.json(
            {"message": "Validation failed.", "details": details}
        ).status(HttpStatus.UNPROCESSABLE_ENTITY)
