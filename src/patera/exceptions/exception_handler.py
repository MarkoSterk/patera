"""
Exception controller implementation
"""

import inspect
from functools import wraps
from typing import Any, Callable, TYPE_CHECKING, Generic, Type, TypeVar

from ..controller.decorators import AsyncMethod, P, R
from ..utilities import run_sync_or_async, _extract_response_type
from ..injectable import Injectable

if TYPE_CHECKING:
    from ..patera import Patera
    from ..response import Response
    from ..request import Request

AppT = TypeVar("AppT", bound="Patera[Any]")


def exception_handler(exc_cls: Type["ExceptionHandler"]) -> Type["ExceptionHandler"]:
    setattr(exc_cls, "_exc_handler", True)
    return exc_cls


class ExceptionHandler(Injectable, Generic[AppT]):
    def __init__(self, app: AppT):
        self._app = app
        self._resolve_injections()

    def get_exception_mapping(self) -> dict[type[BaseException], Callable]:
        """Maps each handled exception class to its handler method."""
        owner_cls: "type[ExceptionHandler]|None" = self.__class__ or None
        handlers: dict[type[BaseException], Callable] = {}
        if owner_cls is None:
            return handlers

        for name in dir(owner_cls):
            if isinstance(inspect.getattr_static(self, name, None), property):
                continue
            method = getattr(self, name, None)
            if method is None or not callable(method):
                continue
            handled_exceptions = getattr(method, "_handled_exceptions", []) or []
            for handled_exception in handled_exceptions:
                handlers[handled_exception] = method

        return handlers

    @property
    def app(self) -> AppT:
        return self._app


def handles(*exceptions: Type[Exception]):
    """Decorator registers exceptions with handler method"""

    def decorator(func: Callable[P, R]) -> AsyncMethod:
        expected_body = _extract_response_type(func)

        @wraps(func)
        async def wrapper(self, *args: P.args, **kwargs: P.kwargs) -> "Response":
            # Request is auto-injected as first arg after self
            if not args:
                raise RuntimeError(
                    "Request must be auto-injected as the first argument after self."
                )
            req: "Request" = args[0]  # type: ignore
            # pylint: disable-next=W0212
            req.response._set_expected_body_type(expected_body)
            res: "Response" = await run_sync_or_async(func, self, *args, **kwargs)
            return res

        handled_exceptions = list(getattr(func, "_handled_exceptions", []) or [])
        handled_exceptions.extend(exceptions)
        # pylint: disable-next=W0212
        wrapper._handled_exceptions = handled_exceptions  # type: ignore[attr-defined]
        return wrapper

    return decorator
