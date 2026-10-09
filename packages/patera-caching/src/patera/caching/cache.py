"""
Caching extension and the @cache route handler decorator.
"""

from __future__ import annotations

from functools import wraps
from typing import (
    Any,
    Callable,
    Generic,
    Optional,
    TypeVar,
    cast,
)
from urllib.parse import urlencode

from patera.utilities import run_sync_or_async
from patera.base_extension import BaseExtension

from .config import CachingConfig
from .backends.base_cache_backend import BaseCacheBackend
from .backends.memory_cache_backend import MemoryCacheBackend
from patera import Patera, Response, Request

__all__ = ["Caching", "CachingConfig", "cache"]


AppT = TypeVar("AppT", bound=Patera[Any], default=Patera[Any])
BackendT = TypeVar("BackendT", bound=BaseCacheBackend, default=BaseCacheBackend)


class Caching(BaseExtension[AppT, CachingConfig], Generic[AppT, BackendT]):
    """
    Caching system for route handlers with **pluggable backend class**.

    Provide a backend instance as the `backend` attribute (class attribute, or
    set in `init()` before calling `super().init()`). It must implement
    BaseCacheBackend. If not provided, an in-memory backend
    (MemoryCacheBackend) configured from the extension's configs is used.

    Default cache duration is set with `DURATION` config (seconds)
    """

    backend: BackendT

    def init(self) -> None:
        self._duration = self.configs.DURATION

        backend = getattr(self, "backend", None)

        if backend is None:
            backend = MemoryCacheBackend()
            backend.configure_from_app(self.app, self.configs)
        elif isinstance(backend, MemoryCacheBackend) and not backend.is_configured:
            backend.configure_from_app(self.app, self.configs)

        self.backend = cast(BackendT, backend)
        self._backend = backend

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
            "status_code": int(value.status_code),
            "headers": dict(value.headers),
            "body": value.body,
            "media_type": value.media_type,
            "charset": value.charset,
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
    ) -> int:
        return await self._backend.delete(key, regex=regex, wildcard=wildcard)

    async def clear(self) -> None:
        await self._backend.clear()

    async def _make_cached_response(self, cached_data: dict, req: Request) -> Response:
        req.res.body = cached_data["body"]
        req.res.status_code = cached_data["status_code"]
        req.res.headers = dict(cached_data["headers"])
        # Entries written by older versions do not carry these keys.
        if cached_data.get("media_type") is not None:
            req.res.media_type = cached_data["media_type"]
            req.res.charset = cached_data.get("charset")
        return req.res


def _is_cacheable(res: Response) -> bool:
    """Only plain, successful, cookie-free responses are shared via the cache."""
    return (
        int(res.status_code) < 400
        and not res.is_streaming
        and res.zero_copy is None
        and not res.cookies
    )


def _default_cache_key(handler: Callable, req: Request) -> str:
    """
    Builds a cache key from the handler, method, path and query string.

    The query string is encoded deterministically (sorted, repeated keys
    preserved) so the key is stable across processes and restarts.
    """
    query = urlencode(sorted(req.query_parameters.items()), doseq=True)
    return f"{handler.__name__}:{req.method}:{req.path}:{query}"


def cache(
    cache_name: str, duration: Optional[int] = None, key: Optional[str] = None
) -> Callable:
    """
    Decorator for caching route handler results using the Caching extension.

    cache_name: registered name of the Caching extension (its UPPER_SNAKE_CASE
        class name, e.g. "PUBLIC_CACHE" for class PublicCache).
    duration: cache duration in seconds (defaults to the extension's DURATION)
    key: fixed cache key. Defaults to handler name + method + path + query.

    Only successful (< 400), non-streaming responses without cookies are cached.
    """

    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(self, *args, **kwargs) -> "Response":
            cache_extension: Caching = self.app._extensions.get(cache_name, None)  # type: ignore
            if cache_extension is None:
                raise RuntimeError(
                    f"Caching extension {cache_name!r} not found in the app."
                )
            req: Request = args[0]
            cache_key = key if key is not None else _default_cache_key(handler, req)

            cached_value: Optional[Response] = await cache_extension.get(cache_key, req)
            if cached_value is not None:
                return cached_value

            res: Response = await run_sync_or_async(handler, self, *args, **kwargs)
            if _is_cacheable(res):
                await cache_extension.set(cache_key, res, duration)
            return res

        return wrapper

    return decorator
