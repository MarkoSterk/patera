"""
In-memory cache implementation
"""

from typing import Generic, Optional, TypeVar, Any, TypedDict
import re
import time

from pydantic import BaseModel

from cachetools import TLRUCache
from fnmatch import fnmatchcase

from .base_cache_backend import BaseCacheBackend
from ..config import CachingConfig
from patera import Patera

AppT = TypeVar("AppT", bound=Patera[Any], default=Patera[Any])


class CacheItem(TypedDict):
    payload: Any
    expire: float


def _expires_at(_key: str, item: CacheItem, _now: float) -> float:
    return item["expire"]


class MemoryCacheBackend(BaseCacheBackend[AppT], Generic[AppT]):
    """
    In-memory cache with a bounded size and per-entry durations.

    Each entry expires after its own duration (``default_ttl`` when none is
    given), like the Redis and SQLite backends; the least recently used
    entries are evicted when ``maxsize`` is reached.
    """

    def __init__(self, default_ttl: int = 300, maxsize: int = 10_000):
        self.default_ttl = default_ttl
        self.maxsize = maxsize
        # Stores: key -> {payload: dict, expire: float}
        self._cache: TLRUCache[str, CacheItem] = TLRUCache(
            maxsize=self.maxsize, ttu=_expires_at, timer=lambda: self._now()
        )

    @classmethod
    def from_configs(
        cls,
        app: AppT,
        configs: CachingConfig | BaseModel | dict[str, Any],
        namespace: str = "cache",
    ) -> "MemoryCacheBackend[AppT]":
        """Creates a backend from DURATION and MAX_SIZE (defaults 300 / 10,000)."""
        values = cls._config_values(configs)
        return cls(
            default_ttl=int(values.get("DURATION") or 300),
            maxsize=int(values.get("MAX_SIZE") or 10_000),
        )

    @staticmethod
    def _now() -> float:
        # Same clock as the cache's timer (time.monotonic); works outside
        # of a running event loop.
        return time.monotonic()

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        self._cache.clear()

    async def get(self, key: str) -> Optional[Any]:
        item = self._cache.get(key)
        if not item:
            return None
        expire = item.get("expire", 0)
        if expire < self._now():
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        return item.get("payload")

    async def set(self, key: str, value: dict, duration: Optional[int] = None) -> None:
        ttl = int(duration) if duration is not None else self.default_ttl
        expire = self._now() + ttl
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
