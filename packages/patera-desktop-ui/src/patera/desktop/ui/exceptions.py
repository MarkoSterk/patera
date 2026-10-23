"""Typed exception dispatch shared by navigation and component events."""

from .controller import methods


class NoRouteMatch(LookupError):
    pass


class APIError(RuntimeError):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"API request failed ({status})")


def handles(*exceptions):
    if any(not isinstance(e, type) or not issubclass(e, Exception) for e in exceptions):
        raise TypeError("Handlers require Exception classes")

    def decorate(function):
        function.__ui_exceptions__ = (
            *getattr(function, "__ui_exceptions__", ()),
            *exceptions,
        )
        return function

    return decorate


class ExceptionHandler:
    def __init__(self, app):
        self.app = app

    def mappings(self):
        for _, method in methods(self):
            for exception in getattr(method, "__ui_exceptions__", ()):
                yield exception, method


class NetworkError(ConnectionError):
    pass


class JsonResponseError(ValueError):
    pass
