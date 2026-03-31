"""
Middleware base class
"""

from abc import abstractmethod, ABC
from patera.injectable import Injectable
from typing import Callable, TYPE_CHECKING, Awaitable, Any, Protocol

from pydantic import BaseModel, ValidationError

from .utilities import run_sync_or_async

if TYPE_CHECKING:
    from .patera import Patera
    from .request import Request
    from .response import Response


# One request in -> Response out (async)
class AppCallableType(Protocol):
    def __call__(self, req: "Request") -> Awaitable["Response"]: ...


# A middleware factory: given (app_instance, next_app) returns a wrapped app
MiddlewareFactory = Callable[["Patera", AppCallableType], AppCallableType]


class MiddlewareBase(Injectable, ABC):
    """
    Base class for middleware
    """

    _configs_name: str | None = None

    def __init__(self, app: "Patera", next_app: AppCallableType):
        """
        Accepts the application and the next part of the middleware chain
        """
        self._app = app
        self._next = next_app
        self._resolve_autowires()

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        value = self.app._extensions.get(target_type.__name__, None)
        if value is None:
            value = target_type()
            if hasattr(value, "init_app"):
                value.init_app(self.app)
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
    def configs_name(self) -> str:
        return (
            self._configs_name
            if self._configs_name
            else self.__class__.__name__.capitalize()
        )

    @property
    def app(self) -> "Patera":
        """
        Returns the application instance
        """
        return self._app

    @property
    def next(self) -> "Callable[[Request], Awaitable[Any]]":
        """
        Returns the next part of the middleware chain
        """
        return self._next
