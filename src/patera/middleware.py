"""
Middleware base class
"""

from abc import abstractmethod, ABC
from patera.injectable import Injectable
from typing import (
    Callable,
    TYPE_CHECKING,
    Awaitable,
    Any,
    Generic,
    Protocol,
    Type,
    TypeVar,
)

from pydantic import BaseModel, ValidationError

from .utilities import run_sync_or_async

if TYPE_CHECKING:
    from .patera import Patera
    from .request import Request
    from .response import Response


# One request in -> Response out (async)
class AppCallableType(Protocol):
    def __call__(self, req: "Request") -> Awaitable["Response"]: ...


def order(order: int = 0) -> Callable[[Type["MiddlewareBase"]], Type["MiddlewareBase"]]:
    """
    Decorator to set the order of middlewares.
    Lower values are processed first. Default order is 0.
    """

    def decorator(cls_type: Type["MiddlewareBase"]) -> Type["MiddlewareBase"]:
        setattr(cls_type, "_order", order)
        return cls_type

    return decorator


AppT = TypeVar("AppT", bound="Patera")


class MiddlewareBase(Injectable, ABC, Generic[AppT]):
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
        self._resolve_autowires()

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        value = self.app._extensions.get(target_type.__name__, None)
        if value is None:
            value = target_type(self.app)
            self.app._extensions[value.configs_name] = value
            self.app._extensions[target_type.__name__] = value
        return value

    def validate_configs(
        self, configs: dict[str, Any], model: type[BaseModel]
    ) -> dict[str, Any]:
        try:
            return model.model_validate(configs).model_dump()
        except ValidationError as e:
            raise ValueError(
                f"Invalid configuration for {self.configs_name or self.__class__.__name__}: {e}"
            ) from e

    @abstractmethod
    async def middleware(self, req: "Request") -> "Response":
        """
        Middleware method to be implemented by subclasses
        """
        ...

    async def __call__(self, req: "Request") -> "Response":
        """
        Middleware call method
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
