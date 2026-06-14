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
    TypeVar,
)

from pydantic import BaseModel

from .utilities import run_sync_or_async, pascal_to_upper_snake

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


def order(order: int = 0) -> Callable[[MiddlewareClsT], MiddlewareClsT]:
    """
    Decorator to set the order of middlewares.
    Lower values are processed first. Default order is 0.
    """

    def decorator(cls_type: MiddlewareClsT) -> MiddlewareClsT:
        setattr(cls_type, "_order", order)
        return cls_type

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

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        name: str = pascal_to_upper_snake(target_type.__name__)
        value = self.app._extensions.get(name, None)
        if value is None:
            value = target_type(self.app)
            self.app._extensions[name] = value
            # self.app._extensions[target_type.__name__] = value
        return value

    def _resolve_config_var(
        self,
        config_name: str,
        declared_type: type[Any],
    ) -> Any:
        value = self.app.get_conf(config_name)

        if isinstance(value, declared_type):
            return value

        try:
            return declared_type(value)
        except Exception as exc:
            raise TypeError(
                f"Config variable {config_name!r} must be of type "
                f"{declared_type.__name__}, got {type(value).__name__}"
            ) from exc

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

    @property
    def configs(self) -> ConfT:
        """Returns the middleware's configuration instance"""
        configs: ConfT = self.app.get_conf(
            self.configs_name, self.app.get_conf(self.__class__.__name__, None)
        )
        if configs is None or not isinstance(configs, BaseModel):
            raise TypeError(f"Invalid configuration for {self.__class__.__name__}")
        return configs
