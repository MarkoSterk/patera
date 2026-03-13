"""
Exception controller implementation
"""

from functools import wraps
from typing import Callable, TYPE_CHECKING, Type

from ..controller.decorators import AsyncMethod, P, R
from ..controller.utilities import _extract_response_type
from ..utilities import run_sync_or_async

if TYPE_CHECKING:
    from ..patera import Patera
    from ..response import Response
    from ..request import Request


class ExceptionHandler:
    def __init__(self, app: "Patera"):
        self._exception_mapping: dict[str, Callable] = {}
        self._app = app

    def get_exception_mapping(self) -> dict[str, Callable]:
        """Produces exception mapping"""
        owner_cls: "type[ExceptionHandler]|None" = self.__class__ or None
        handlers: dict[str, Callable] = {}
        if owner_cls is None:
            return handlers

        for name in dir(owner_cls):
            method = getattr(self, name)
            if not callable(method):
                continue
            handled_exceptions = getattr(method, "_handled_exceptions", []) or []
            for handled_exception in handled_exceptions:
                handlers[handled_exception.__name__] = method

        self._exception_mapping = handlers
        return handlers

    @property
    def app(self) -> "Patera":
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

        handled_exceptions = getattr(func, "_handled_exceptions", []) or []
        handled_exceptions.extend(list(exceptions))
        # pylint: disable-next=W0212
        wrapper._handled_exceptions = handled_exceptions  # type: ignore[attr-defined]
        return wrapper

    return decorator
