"""Exception handler module"""

from typing import TYPE_CHECKING, Type, Callable

if TYPE_CHECKING:
    from ..app import Application


class ExceptionController:
    def __init__(self, app: "Application"):
        self._app = app
        self.get_exception_mapping()

    def get_exception_mapping(self) -> dict[str, Callable]:
        """Produces exception mapping"""
        owner_cls: "Type[ExceptionController]|None" = self.__class__ or None
        handlers: dict[str, Callable] = {}
        if owner_cls is None:
            return handlers

        for name in dir(owner_cls):
            method = getattr(self, name)
            if not callable(method):
                continue
            handles_exceptions = getattr(method, "__handles_exceptions", []) or []
            for handles_exception in handles_exceptions:
                handlers[handles_exception.__name__] = method
        return handlers

    @property
    def app(self) -> "Application":
        return self._app


def handles(*exceptions: Type[Exception]):
    """Decorator registers exceptions with handler method"""

    def decorator(func: Callable) -> Callable:
        handles_exceptions = getattr(func, "__handles_exceptions", []) or []
        handles_exceptions.extend(list(exceptions))
        setattr(func, "__handles_exceptions", handles_exceptions)
        return func

    return decorator
