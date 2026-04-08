""" """

from __future__ import annotations

from functools import wraps
from typing import (
    Callable,
    Generic,
    NotRequired,
    Optional,
    Type,
    TypeVar,
    TypedDict,
    cast,
    TYPE_CHECKING,
    Any,
)
from pydantic import BaseModel, Field

from patera.utilities import run_sync_or_async
from patera.base_extension import BaseExtension

from .backends.base_cache_backend import BaseCacheBackend

if TYPE_CHECKING:
    from patera import Patera, Response, Request


class _CachingConfigs(BaseModel):
    """Configuration model for Caching extension."""

    BACKEND: Optional[Type[BaseCacheBackend]] = Field(
        default=None,
        description="Caching backend class, must be subclass of BaseCacheBackend",
    )
    DURATION: Optional[int] = Field(
        default=300, description="Default cache duration in seconds"
    )


class CachingConfig(TypedDict):
    """Cache configurations"""

    BACKEND: NotRequired[Type[BaseCacheBackend]]
    DURATION: NotRequired[int]


AppT = TypeVar("AppT", bound="Patera")


class Caching(BaseExtension[AppT], Generic[AppT]):
    """
    Caching system for route handlers with **pluggable backend class**.

    Provide caching implementation as `BACKEND` config. This should be
    a valid caching implementation of the BaseCacheBackend class.
    If not provided, defaults to in-memory caching (MemoryCacheBackend).

    Default cache duration is set with `DURATION` config (seconds)
    """

    def __init__(self) -> None:
        self._app: AppT = cast(AppT, None)
        self._duration: int = 300
        self._backend: Optional[BaseCacheBackend] = None
        self._configs: dict[str, Any] = {}

    def init_app(self, app: AppT) -> None:
        self._app = app  # type: ignore
        self._configs = self.load_configs() or {}
        self._configs = self.validate_configs(self._configs, _CachingConfigs)

        self._duration = self._configs["DURATION"]
        backend_cls = self._configs.get("BACKEND", None)
        if backend_cls is None:
            # loads default backend - MemoryCacheBackend
            # pylint: disable-next=C0415
            from .backends.memory_cache_backend import MemoryCacheBackend

            backend_cls = MemoryCacheBackend
        if not issubclass(backend_cls, BaseCacheBackend):
            raise TypeError(
                "CACHE_BACKEND must be a class and subclass of BaseCacheBackend"
            )

        self._backend = cast(Type[BaseCacheBackend], backend_cls).configure_from_app(
            app, self._configs
        )

        # self._app.add_extension(self)
        self._app.add_on_startup_method(self.connect)
        self._app.add_on_shutdown_method(self.disconnect)

    async def connect(self) -> None:
        if self._backend:
            await self._backend.connect()

    async def disconnect(self) -> None:
        if self._backend:
            await self._backend.disconnect()

    async def set(
        self, key: str, value: "Response", duration: Optional[int] = None
    ) -> None:
        cached_value = {
            "status_code": value.status_code,
            "headers": value.headers,
            "body": value.body,
        }
        if duration is None:
            duration = self._duration
        await cast(BaseCacheBackend, self._backend).set(key, cached_value, duration)

    async def get(self, key: str, req: "Request") -> "Optional[Response]":
        payload = await cast(BaseCacheBackend, self._backend).get(key)
        if payload is None:
            return None
        return await self._make_cached_response(payload, req)

    async def delete(self, key: str) -> None:
        await cast(BaseCacheBackend, self._backend).delete(key)

    async def clear(self) -> None:
        await cast(BaseCacheBackend, self._backend).clear()

    async def _make_cached_response(
        self, cached_data: dict, req: "Request"
    ) -> "Response":
        req.res.body = cached_data["body"]
        req.res.status_code = cached_data["status_code"]
        req.res.headers = cached_data["headers"]
        return req.res


def cache(cls: Type[Caching], duration: Optional[int] = None) -> Callable:
    """Decorator for caching route handler results using the Caching extension."""

    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(self, *args, **kwargs) -> "Response":
            cache_extension: Caching = self.app._extensions.get(cls.__name__, None)  # type: ignore
            if cache_extension is None:
                raise RuntimeError("Caching extension not found in the app.")
            req: Request = args[0]
            method: str = req.method
            path: str = req.path
            query_params = sorted(req.query_params.items())
            cache_key = (
                f"{handler.__name__}:{method}:{path}:{hash(frozenset(query_params))}"
            )

            cached_value: Optional[Response] = await cache_extension.get(cache_key, req)
            if cached_value is not None:
                return cached_value

            res: Response = await run_sync_or_async(handler, self, *args, **kwargs)
            await cache_extension.set(cache_key, res, duration)
            return res

        return wrapper

    return decorator
