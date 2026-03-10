"""Controller class for endpoint groups"""

from __future__ import annotations
from typing import Callable, TYPE_CHECKING, Optional, Type, TypeVar

from pydantic import BaseModel
from ..media_types import MediaType
from ..http_statuses import HttpStatus

if TYPE_CHECKING:
    from ..pyjolt import PyJolt

T = TypeVar("T", bound="Controller")


def path(
    url_path: str = "/", open_api_spec: bool = True, tags: Optional[list[str]] = None
) -> "Callable":
    def decorator(cls: "Type[Controller]") -> "Type[Controller]":
        setattr(cls, "_controller_path", url_path)
        setattr(cls, "_include_open_api_spec", open_api_spec)
        setattr(cls, "_open_api_tags", tags)
        return cls

    return decorator


class Controller:
    # _controller_decorator_methods: list[Callable]

    def __init__(
        self,
        app: "PyJolt",
        url_path: str = "/",
        open_api_spec: bool = True,
        open_api_tags: Optional[list[str]] = None,
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
        self.get_before_request_methods()
        self.get_after_request_methods()

    def get_endpoint_methods(self) -> dict[str, dict[str, str | Callable]]:
        """Returns a dictionery with all endpoint methods"""
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
            method = getattr(self, name)
            if not callable(method):
                continue
            endpoint_handler = getattr(method, "_handler", None)
            if endpoint_handler:
                dev_only: bool = getattr(method, "_development", False)
                if dev_only and not self.app.get_conf("DEBUG", False):
                    continue
                if endpoint_handler.get("tags") is not None:
                    endpoint_handler["tags"].extend(self._open_api_tags)
                http_method: str = endpoint_handler.get("http_method")  # type: ignore
                endpoints[http_method.upper()][endpoint_handler["path"]] = {
                    "method": method,
                    "base_path": self._path,
                    **endpoint_handler,
                }
        self._endpoints_map = endpoints
        return endpoints

    def get_before_request_methods(self):
        owner_cls = self.__class__ or None
        if owner_cls is None:
            return

        for name in dir(self):
            method = getattr(self, name)
            if not callable(method):
                continue
            handler = getattr(method, "_before_request", None)
            if handler:
                self._before_request_methods.append(method)

    def get_after_request_methods(self):
        owner_cls = self.__class__ or None
        if owner_cls is None:
            return

        for name in dir(self):
            method = getattr(self, name)
            if not callable(method):
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
    def app(self) -> "PyJolt":
        """App object"""
        return self._app


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
