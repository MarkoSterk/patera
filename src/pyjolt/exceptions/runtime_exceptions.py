"""
Custom exception classes for PyJolt
"""


class CustomException(Exception):
    """Base custom exception class"""


class MethodNotControllerMethod(CustomException):
    """
    Error if the decorated method is not part of a controller
    """

    def __init__(self, message):
        self.message = message


class UnexpectedDecorator(CustomException):
    """
    Error for unexpected decorators
    """

    def __init__(self, message):
        self.message = message
