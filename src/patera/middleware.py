"""
Middleware base class
"""

from abc import abstractmethod, ABC
from patera.injectable import Injectable, resolve_component_configs
from typing import (
    Callable,
    ClassVar,
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
    Base class for middleware.

    ``middleware(self, req)`` may declare Headers[...], Cookies[...] and
    QueryParams[...] parameters after ``req``; they are validated (422 when
    invalid) and passed on every request:

        async def middleware(self, req, tenant: Headers[TenantHeaders]):
            ...

    Their fields are documented on every OpenAPI operation, unless the
    class sets ``open_api_spec = False`` (for middleware that only acts on
    some paths).
    """

    #: Document this middleware's Headers/Cookies/QueryParams on every
    #: OpenAPI operation.
    open_api_spec: ClassVar[bool] = True

    def __init__(
        self, app: AppT, next_app: "Callable[[Request], Awaitable[Response]]"
    ) -> None:
        """
        Accepts the application and the next part of the middleware chain
        """
        self._app = app
        self._next = next_app
        self._resolve_injections()
        # Fails at startup for parameters nothing would fill.
        self._param_plan = self._middleware_plan()

    def _middleware_plan(self) -> Any:
        # Imported here: the controller package is imported after this module.
        # pylint: disable-next=C0415
        from .controller.params import check_request_hook_params

        return check_request_hook_params(
            self.middleware, f"{type(self).__name__}.middleware"
        )

    @abstractmethod
    async def middleware(
        self, req: "Request", /, *args: Any, **kwargs: Any
    ) -> "Response":
        """
        Middleware method to be implemented by subclasses: ``(self, req)``,
        optionally followed by Headers[...], Cookies[...] and QueryParams[...]
        parameters.
        """
        ...

    async def __call__(self, req: "Request") -> "Response":
        """
        Runs this middleware's ``middleware`` method. That method continues
        the chain by awaiting ``self.next(req)``, or returns a response
        without calling it to short-circuit the request.
        """
        plan = self.__dict__.get("_param_plan")
        if plan is None:  # a subclass __init__ that skipped super().__init__
            plan = self.__dict__["_param_plan"] = self._middleware_plan()
        if not plan.has_sources:
            return await run_sync_or_async(self.middleware, req)
        # pylint: disable-next=C0415
        from .controller.utilities import bind_request_values

        return await run_sync_or_async(
            self.middleware, req, **bind_request_values(req, plan)
        )

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
