"""
Custom exception classes for Patera
"""


class CustomException(Exception):
    """Base custom exception class"""


class MethodNotControllerMethod(CustomException):
    """
    Error if the decorated method is not part of a controller
    """

    def __init__(self, message):
        self.message = message


class ClientDisconnected(CustomException):
    """
    Raised when the client disconnects before its request body has arrived
    completely. The handler is stopped (and a transaction rolled back), and
    no response is sent, since nobody is left to receive it.
    """


class DuplicateRouteError(CustomException, ValueError):
    """
    Raised when two different handlers are registered for the same HTTP
    method and path.
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class CircularDependencyError(CustomException, RuntimeError):
    """
    Raised when injected dependencies require each other in a cycle.
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class UnexpectedDecorator(CustomException):
    """
    Error for unexpected decorators
    """

    def __init__(self, message):
        self.message = message
