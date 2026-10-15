"""
Caching extension and the @cache route handler decorator.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
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

from patera.utilities import pascal_to_upper_snake, run_sync_or_async
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

    The backend is chosen in one of two ways:

    - ``backend_class`` (default MemoryCacheBackend): the extension creates it
      with ``backend_class.from_configs(app, configs)`` from its settings,
      for example ``backend_class = RedisCacheBackend`` with REDIS_URL and
      KEY_PREFIX in the configuration.
    - ``backend``: an instance you construct yourself (as a class attribute,
      or in ``init()`` before calling ``super().init()``). It is used as it
      is, without reading the configuration.

    Default cache duration is set with `DURATION` config (seconds).
    """

    backend: BackendT
    backend_class: type[BaseCacheBackend] = MemoryCacheBackend

    def init(self) -> None:
        self._duration = self.configs.DURATION

        backend = getattr(self, "backend", None)

        if backend is None:
            backend = self.backend_class.from_configs(
                self.app, self.configs, namespace=self.cache_name
            )

        self.backend = cast(BackendT, backend)
        self._backend = backend

        self._app.add_on_startup_method(self.connect)
        self._app.add_on_shutdown_method(self.disconnect)

    @property
    def cache_name(self) -> str:
        """
        The configuration name in lower case (PublicCache -> "public_cache").
        Shared backends (Redis, SQLite) use it in their default key prefix.
        """
        return pascal_to_upper_snake(type(self).__name__).lower()

    async def connect(self) -> None:
        await self._backend.connect()

    async def disconnect(self) -> None:
        await self._backend.disconnect()

    async def set(
        self, key: str, value: Response, duration: Optional[int] = None
    ) -> None:
        """
        Caches a response as it will be sent: the body is serialized first
        (through the handler's Response[Model] annotation, like every
        response) and stored as bytes. The cache therefore holds no Python
        objects, and backends store plain JSON.
        """
        body = await self.app.response_renderer.render_body(
            value, value.expected_body_type()
        )
        cached_value = {
            "status_code": int(value.status_code),
            "status_set": value.status_set,
            "headers": dict(value.headers),
            "body": None if body is None else base64.b64encode(body).decode("ascii"),
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

    def user_cache_key(self, req: Request) -> Optional[str]:
        """
        Returns the part of the cache key that identifies the signed-in user,
        or None for an anonymous request. The default uses the user's ``id``
        (or ``pk``) attribute or key, and falls back to ``str(user)``.
        Override it when users are identified differently.
        """
        user = req.user
        if user is None:
            return None
        for name in ("id", "pk"):
            value = (
                user.get(name)
                if isinstance(user, Mapping)
                else getattr(user, name, None)
            )
            if value is not None:
                return str(value)
        return str(user)

    async def _make_cached_response(self, cached_data: dict, req: Request) -> Response:
        body = cached_data.get("body")
        req.res.body = None if body is None else base64.b64decode(body)
        req.res.status_code = cached_data["status_code"]
        # Keeps a decorator default such as @produces' status code working
        # the same on a hit as on a miss.
        req.res._status_set = bool(cached_data.get("status_set", False))
        req.res.headers = dict(cached_data["headers"])
        req.res.media_type = cached_data["media_type"]
        req.res.charset = cached_data["charset"]
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
    cache_name: str,
    duration: Optional[int] = None,
    key: Optional[str] = None,
    per_user: bool = True,
) -> Callable:
    """
    Decorator for caching route handler results using the Caching extension.

    cache_name: registered name of the Caching extension (its UPPER_SNAKE_CASE
        class name, e.g. "PUBLIC_CACHE" for class PublicCache).
    duration: cache duration in seconds (defaults to the extension's DURATION)
    key: fixed cache key. Defaults to handler name + method + path + query.
    per_user: when True (the default), a signed-in user gets an entry of their
        own, so a response that depends on who asks is never served to
        someone else. Anonymous requests share one entry. Set it to False
        for responses that are the same for everyone.

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
            if per_user:
                user_key = cache_extension.user_cache_key(req)
                if user_key is not None:
                    cache_key = f"{cache_key}:user:{user_key}"

            cached_value: Optional[Response] = await cache_extension.get(cache_key, req)
            if cached_value is not None:
                return cached_value

            res: Response = await run_sync_or_async(handler, self, *args, **kwargs)
            if _is_cacheable(res):
                await cache_extension.set(cache_key, res, duration)
            return res

        return wrapper

    return decorator
