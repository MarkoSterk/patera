class ExamError(Exception):
    """A rule of the exam domain was broken. Mapped to HTTP in app/exceptions."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(ExamError):
    pass


class Forbidden(ExamError):
    pass


class Conflict(ExamError):
    pass


class InvalidCredentials(ExamError):
    pass


def require(
    condition: object, message: str, error: type[ExamError] = ExamError
) -> None:
    if not condition:
        raise error(message)
