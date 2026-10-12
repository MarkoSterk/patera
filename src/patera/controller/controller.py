"""Controller class for endpoint groups"""

from __future__ import annotations
import inspect
from typing import Any, Callable, TYPE_CHECKING, Optional, Type, TypeVar, Generic

from pydantic import BaseModel
from ..media_types import MediaType
from ..http_statuses import HttpStatus
from ..injectable import Injectable
from ..utilities import run_sync_or_async
from ..exceptions.runtime_exceptions import DuplicateRouteError

if TYPE_CHECKING:
    from ..patera import Patera, Request, Response

AppT = TypeVar("AppT", bound="Patera[Any]")
T = TypeVar("T", bound="Controller[Any]")


def _same_function(first: Callable, second: Callable) -> bool:
    """True if two (bound) callables wrap the same underlying function."""
    return getattr(first, "__func__", first) is getattr(second, "__func__", second)


def path(
    url_path: str = "/",
    open_api_spec: bool = True,
    tags: Optional[list[str]] = None,
    alias: Optional[str] = None,
) -> "Callable":
    def decorator(cls: "Type[Controller]") -> "Type[Controller]":
        setattr(cls, "_controller_path", url_path)
        setattr(cls, "_include_open_api_spec", open_api_spec)
        setattr(cls, "_open_api_tags", tags)
        setattr(cls, "_alias", alias)
        return cls

    return decorator


class Controller(Injectable, Generic[AppT]):
    # _controller_decorator_methods: list[Callable]

    def __init__(
        self,
        app: AppT,
        url_path: str = "/",
        open_api_spec: bool = True,
        open_api_tags: Optional[list[str]] = None,
        alias: Optional[str] = None,
    ):
        self._app = app
        self._path = url_path
        self._before_request_methods: list[Callable] = []
        self._after_request_methods: list[Callable] = []
        self._endpoints_map: dict[str, dict[str, str | Callable | dict]] = {}
        self._open_api_spec = open_api_spec
        self._open_api_tags = (
            open_api_tags if open_api_tags is not None else [self.__class__.__name__]
        )
        self._alias = alias
        self.get_before_request_methods()
        self.get_after_request_methods()
        self._resolve_injections()
        self._after_init_methods()

    def _after_init_methods(self):
        for name in dir(self):
            method = getattr(self, name, None)
            if method is None or not callable(method):
                continue
            after_init_handler = getattr(method, "_after_init", False)
            if after_init_handler:
                method()

    def get_endpoint_methods(self) -> dict[str, dict[str, str | Callable]]:
        """
        Returns the controller's endpoints by HTTP method and path.

        Raises DuplicateRouteError if two different methods are registered
        for the same HTTP method and path.
        """
        owner_cls: "type[Controller]|None" = self.__class__ or None
        endpoints: dict[str, dict] = {
            "GET": {},
            "POST": {},
            "PUT": {},
            "PATCH": {},
            "DELETE": {},
            "SOCKET": {},
        }
        if owner_cls is None:
            return endpoints

        for name in dir(self):
            method = getattr(self, name, None)
            if method is None or not callable(method):
                continue
            endpoint_handler = getattr(method, "_handler", None)
            if endpoint_handler:
                dev_only: bool = getattr(method, "_development", False)
                ignore: bool = getattr(method, "_ignore", False)
                if ignore or (dev_only and not self.app.get_conf("DEBUG", False)):
                    continue
                # Copy: the handler dict is shared by every instance of the
                # controller class (and every app that registers it).
                handler_info: dict[str, Any] = dict(endpoint_handler)
                if handler_info.get("tags") is not None:
                    handler_info["tags"] = [
                        *handler_info["tags"],
                        *self._open_api_tags,
                    ]
                http_method: str = handler_info.get("http_method")  # type: ignore
                existing = endpoints[http_method.upper()].get(handler_info["path"])
                if existing is not None and _same_function(existing["method"], method):
                    # The same function reachable under a second attribute name.
                    continue
                if existing is not None:
                    raise DuplicateRouteError(
                        f"{owner_cls.__name__}: methods "
                        f"{existing['method'].__name__!r} and {name!r} are both "
                        f"registered for {http_method.upper()} "
                        f"{handler_info['path']!r}."
                    )
                endpoints[http_method.upper()][handler_info["path"]] = {
                    "method": method,
                    "base_path": self._path,
                    **handler_info,
                }
        self._endpoints_map = endpoints
        return endpoints

    def get_before_request_methods(self):
        owner_cls = self.__class__ or None
        if owner_cls is None:
            return

        for name in dir(self):
            method = getattr(self, name, None)
            if method is None or not callable(method):
                continue
            handler = getattr(method, "_before_request", None)
            if handler:
                self._before_request_methods.append(method)

    def get_after_request_methods(self):
        owner_cls = self.__class__ or None
        if owner_cls is None:
            return

        for name in dir(self):
            method = getattr(self, name, None)
            if method is None or not callable(method):
                continue
            handler = getattr(method, "_after_request", None)
            if handler:
                self._after_request_methods.append(method)

    @property
    def endpoints_map(self) -> dict[str, dict[str, str | Callable | dict]]:
        """Returns map of all endpoints"""
        return self._endpoints_map

    @property
    def path(self) -> str:
        """Path variable of the class"""
        return self._path

    @property
    def open_api_spec(self) -> bool:
        """If it is included in the open api specs"""
        return self._open_api_spec

    @property
    def app(self) -> AppT:
        """App object"""
        return self._app

    @property
    def alias(self) -> Optional[str]:
        """Alias for the controller, used in url_for"""
        return self._alias

    async def __call__(self, method: Callable, req: "Request") -> "Response":
        """
        Handles request method call with before and after methods.
        """
        sig = inspect.signature(method)
        kwargs: dict[str, Any] = {}
        for name, _ in sig.parameters.items():
            if name in req.route_parameters:
                kwargs[name] = req.route_parameters[name]
        for br_method in self._before_request_methods:
            await run_sync_or_async(br_method, req)
        res: "Response" = await run_sync_or_async(method, req, **kwargs)
        for ar_method in self._after_request_methods:
            await run_sync_or_async(ar_method, res)
        return res


class Descriptor:
    def __init__(
        self,
        status: int | HttpStatus = HttpStatus.BAD_REQUEST,
        description: Optional[str] = None,
        media_type: MediaType = MediaType.APPLICATION_JSON,
        body: Optional[Type[BaseModel]] = None,
    ):
        if isinstance(status, HttpStatus):
            status = status.value
        self._status = status
        self._description = description
        self._body = body
        self._media_type = media_type

    @property
    def status(self) -> HttpStatus | int:
        return self._status

    @property
    def description(self) -> Optional[str]:
        return self._description

    @property
    def body(self) -> Optional[Type[BaseModel]]:
        return self._body

    @property
    def media_type(self) -> MediaType:
        return self._media_type
