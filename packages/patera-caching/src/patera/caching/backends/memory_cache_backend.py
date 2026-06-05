"""
In-memory cache implementation
"""

from typing import Generic, Optional, TypeVar, cast, Any, TypedDict
import asyncio
import re

from cachetools import TTLCache
from fnmatch import fnmatchcase

from .base_cache_backend import BaseCacheBackend
from ..cache import CachingConfig
from patera import Patera

AppT = TypeVar("AppT", bound=Patera[Any], default=Patera[Any])


class CacheItem(TypedDict):
    payload: Any
    expire: float


class MemoryCacheBackend(BaseCacheBackend[AppT], Generic[AppT]):
    """
    In-memory cache using cachetools.TTLCache for bounded size and base TTL.


    Per-item TTL by storing an explicit expire timestamp alongside
    the payload; TTLCache provides a global upper bound and eviction.
    """

    def __init__(self, default_ttl: int = 300, maxsize: int = 10_000):
        self.default_ttl = default_ttl
        self.maxsize = maxsize
        # Stores: key -> {payload: dict, expire: float}
        self._cache: TTLCache[str, CacheItem] = cast(
            TTLCache[str, CacheItem], None
        )  # Initialized in configure_from_app

    def configure_from_app(self, app: AppT, configs: CachingConfig) -> None:
        self.default_ttl = (
            configs.DURATION if configs.DURATION is not None else self.default_ttl
        )
        self.maxsize = (
            configs.MAX_SIZE if configs.MAX_SIZE is not None else self.maxsize
        )
        self._cache = TTLCache(maxsize=self.maxsize, ttl=self.default_ttl)

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        self._cache.clear()

    async def get(self, key: str) -> Optional[Any]:
        item = self._cache.get(key)
        if not item:
            return None
        expire = item.get("expire", 0)
        if expire < asyncio.get_event_loop().time():
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        return item.get("payload")

    async def set(self, key: str, value: dict, duration: Optional[int] = None) -> None:
        ttl = int(duration) if duration is not None else self.default_ttl
        expire = asyncio.get_event_loop().time() + ttl
        self._cache[key] = {"payload": value, "expire": expire}

    async def delete(
        self,
        key: str,
        *,
        regex: bool = False,
        wildcard: bool = False,
    ) -> int:
        """
        Delete cache entries.

        Exact delete:
            await delete("handler:GET:/users")

        Wildcard delete:
            await delete("handler:*", wildcard=True)

        Regex delete:
            await delete(r"^handler:GET:/users/.*", regex=True)

        Returns the number of deleted entries.
        """

        if regex and wildcard:
            raise ValueError("Use either regex=True or wildcard=True, not both.")

        # Remove expired entries before scanning.
        self._cache.expire()

        if not regex and not wildcard:
            try:
                del self._cache[key]
                return 1
            except KeyError:
                return 0

        keys = list(self._cache.keys())

        if regex:
            pattern = re.compile(key)
            keys_to_delete = [
                cache_key for cache_key in keys if pattern.search(cache_key)
            ]
        else:
            keys_to_delete = [
                cache_key for cache_key in keys if fnmatchcase(cache_key, key)
            ]

        deleted = 0

        for cache_key in keys_to_delete:
            try:
                del self._cache[cache_key]
                deleted += 1
            except KeyError:
                pass

        return deleted

    async def clear(self) -> None:
        self._cache.clear()
