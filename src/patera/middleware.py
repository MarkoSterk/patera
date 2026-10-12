"""
Middleware base class
"""

from abc import abstractmethod, ABC
from patera.injectable import Injectable, resolve_component_configs
from typing import (
    Callable,
    TYPE_CHECKING,
    Awaitable,
    Any,
    Generic,
    TypeAlias,
    cast,
    overload,
    Protocol,
    TypeVar,
)

from pydantic import BaseModel

from .utilities import run_sync_or_async

if TYPE_CHECKING:
    from .patera import Patera
    from .request import Request
    from .response import Response


# One request in -> Response out (async)
class AppCallableType(Protocol):
    def __call__(self, req: "Request") -> Awaitable["Response"]: ...


MiddlewareClsT = TypeVar(
    "MiddlewareClsT",
    bound=type["MiddlewareBase[Any, Any]"],
)

MiddlewareDecorator: TypeAlias = Callable[[MiddlewareClsT], MiddlewareClsT]


@overload
def middleware(cls: MiddlewareClsT) -> MiddlewareClsT: ...
@overload
def middleware(*, order: int | None = None) -> MiddlewareDecorator: ...
def middleware(
    cls: MiddlewareClsT | None = None,
    *,
    order: int | None = None,
) -> MiddlewareClsT | MiddlewareDecorator:
    """
    Decorator to mark a middleware implementation as middleware to be used by the application.

    ``order`` sets the middleware's position in the chain; lower orders run
    first on the way in. It must be greater than 0, because negative orders
    are reserved for the framework's own middleware (CORS -101, database
    sessions -100, authentication -99). A middleware registered without an
    order, here or in ``register_middleware``, raises ValueError. If two
    classes ask for the same order, the later one moves to the next free
    number and a warning is logged.
    """
    if order is not None and order <= 0:
        raise ValueError("Middleware order must be greater than 0.")

    def decorator(target_cls: MiddlewareClsT) -> MiddlewareClsT:
        setattr(target_cls, "_order", order)
        setattr(target_cls, "_middleware", True)
        return target_cls

    if cls is not None:
        return decorator(cls)

    return decorator


AppT = TypeVar("AppT", bound="Patera[Any]")
ConfT = TypeVar("ConfT", bound=BaseModel, default=BaseModel)


class MiddlewareBase(Injectable, ABC, Generic[AppT, ConfT]):
    """
    Base class for middleware
    """

    def __init__(
        self, app: AppT, next_app: "Callable[[Request], Awaitable[Response]]"
    ) -> None:
        """
        Accepts the application and the next part of the middleware chain
        """
        self._app = app
        self._next = next_app
        self._resolve_injections()

    @abstractmethod
    async def middleware(self, req: "Request") -> "Response":
        """
        Middleware method to be implemented by subclasses
        """
        ...

    async def __call__(self, req: "Request") -> "Response":
        """
        Runs this middleware's ``middleware`` method. That method continues
        the chain by awaiting ``self.next(req)``, or returns a response
        without calling it to short-circuit the request.
        """
        return await run_sync_or_async(self.middleware, req)

    @property
    def app(self) -> AppT:
        """
        Returns the application instance
        """
        return self._app

    @property
    def next(self) -> "Callable[[Request], Awaitable[Response]]":
        """
        Returns the next part of the middleware chain
        """
        return self._next

    @property
    def configs(self) -> ConfT:
        """
        Returns the middleware's configuration instance.

        Dictionaries are validated with the declared config model and a
        missing configuration falls back to the model's defaults.
        """
        cached = self.__dict__.get("_resolved_configs")
        if cached is None:
            cached = resolve_component_configs(self, MiddlewareBase)
            self.__dict__["_resolved_configs"] = cached
        return cast(ConfT, cached)
