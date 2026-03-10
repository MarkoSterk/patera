"""
Middleware base class
"""

from abc import abstractmethod, ABC
from typing import Callable, TYPE_CHECKING, Awaitable, Any, Protocol

from pydantic import BaseModel, ValidationError

from .utilities import run_sync_or_async

if TYPE_CHECKING:
    from .pyjolt import PyJolt
    from .request import Request
    from .response import Response


# One request in -> Response out (async)
class AppCallableType(Protocol):
    def __call__(self, req: "Request") -> Awaitable["Response"]: ...


# A middleware factory: given (app_instance, next_app) returns a wrapped app
MiddlewareFactory = Callable[["PyJolt", AppCallableType], AppCallableType]


class MiddlewareBase(ABC):
    """
    Base class for middleware
    """

    configs_name: str

    def __init__(self, app: "PyJolt", next_app: AppCallableType):
        """
        Accepts the application and the next part of the middleware chain
        """
        self._app = app
        self._next = next_app

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
    def app(self) -> "PyJolt":
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
