""" """

from __future__ import annotations

from functools import wraps
from typing import (
    Any,
    Callable,
    Generic,
    Optional,
    Type,
    TypeVar,
)
from pydantic import BaseModel, Field

from patera.utilities import run_sync_or_async
from patera.base_extension import BaseExtension

from .backends.base_cache_backend import BaseCacheBackend
from patera import Patera, Response, Request


class CachingConfig(BaseModel):
    """Configuration model for Caching extension."""

    DURATION: Optional[int] = Field(
        None, description="Default cache duration in seconds"
    )
    MAX_SIZE: Optional[int] = Field(
        None,
        description="Maximum number of items in the cache (if supported by backend)",
    )


AppT = TypeVar("AppT", bound=Patera[Any], default=Patera[Any])
BackendT = TypeVar("BackendT", bound=BaseCacheBackend, default=BaseCacheBackend)


class Caching(BaseExtension[AppT, CachingConfig], Generic[AppT, BackendT]):
    """
    Caching system for route handlers with **pluggable backend class**.

    Provide caching implementation as `backend` class variable. This should be
    a valid caching implementation of the BaseCacheBackend class.
    If not provided, defaults to in-memory caching (MemoryCacheBackend).

    Default cache duration is set with `DURATION` config (seconds)
    """

    backend: BackendT

    def init(self) -> None:

        self._duration = self.configs.DURATION

        self._backend = self.backend

        # self._app.add_extension(self)
        self._app.add_on_startup_method(self.connect)
        self._app.add_on_shutdown_method(self.disconnect)

    async def connect(self) -> None:
        await self._backend.connect()

    async def disconnect(self) -> None:
        await self._backend.disconnect()

    async def set(
        self, key: str, value: Response, duration: Optional[int] = None
    ) -> None:
        cached_value = {
            "status_code": value.status_code,
            "headers": value.headers,
            "body": value.body,
        }
        if duration is None:
            duration = self._duration
        await self._backend.set(key, cached_value, duration)

    async def get(self, key: str, req: Request) -> Optional[Response]:
        payload = await self._backend.get(key)
        if payload is None:
            return None
        return await self._make_cached_response(payload, req)

    async def delete(
        self,
        key: str,
        *,
        regex: bool = False,
        wildcard: bool = False,
    ) -> None:
        await self._backend.delete(key, regex=regex, wildcard=wildcard)

    async def clear(self) -> None:
        await self._backend.clear()

    async def _make_cached_response(self, cached_data: dict, req: Request) -> Response:
        req.res.body = cached_data["body"]
        req.res.status_code = cached_data["status_code"]
        req.res.headers = cached_data["headers"]
        return req.res


def cache(
    cls: Type[Caching], duration: Optional[int] = None, key: Optional[str] = None
) -> Callable:
    """Decorator for caching route handler results using the Caching extension."""

    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(self, *args, **kwargs) -> Response:
            cache_extension: Caching = self.app._extensions.get(cls.__name__, None)  # type: ignore
            if cache_extension is None:
                raise RuntimeError("Caching extension not found in the app.")
            req: Request = args[0]
            method: str = req.method
            path: str = req.path
            query_params = sorted(req.query_parameters.items())
            cache_key = (
                key
                if key is not None
                else (
                    f"{handler.__name__}:{method}:{path}:{hash(frozenset(query_params))}"
                )
            )

            cached_value: Optional[Response] = await cache_extension.get(cache_key, req)
            if cached_value is not None:
                return cached_value

            res: Response = await run_sync_or_async(handler, self, *args, **kwargs)
            await cache_extension.set(cache_key, res, duration)
            return res

        return wrapper

    return decorator
