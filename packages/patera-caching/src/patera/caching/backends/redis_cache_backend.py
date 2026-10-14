"""
Redis cache implementation

Settings of the cache extension that uses it:
REDIS_URL       = "redis://localhost:6379/0"   # required
REDIS_PASSWORD  = None                          # optional
DURATION        = 300                           # optional (default TTL)
KEY_PREFIX      = "patera:<app>:<cache>:"      # optional prefix/namespace

Every key lives under the prefix, and clear() deletes only those keys. An
empty prefix is allowed for get/set/delete, but clear() then refuses to run,
because it would flush the whole Redis database, including data that other
applications keep there.
"""

from __future__ import annotations

import re
from typing import Generic, Optional, TypeVar, cast, List, TYPE_CHECKING, Any

from pydantic import BaseModel
from redis.asyncio import Redis, from_url

from .base_cache_backend import BaseCacheBackend

DEFAULT_KEY_PREFIX = "patera:cache:"

if TYPE_CHECKING:
    from patera import Patera

AppT = TypeVar("AppT", bound="Patera", default="Patera")


class RedisCacheBackend(BaseCacheBackend[AppT], Generic[AppT]):
    """Redis-backed cache storing JSON payloads."""

    def __init__(
        self,
        url: str,
        password: Optional[str] = None,
        default_ttl: int = 300,
        key_prefix: str = DEFAULT_KEY_PREFIX,
    ) -> None:
        if not url:
            raise ValueError("REDIS_URL must be set for RedisCacheBackend")
        self._url = url
        self._password = password
        self._client: Optional[Redis] = None
        self.default_ttl = int(default_ttl)
        # Normalize prefix to empty or end with ':' for nicer namespaces
        key_prefix = key_prefix or ""
        if key_prefix and not key_prefix.endswith(":"):
            key_prefix = key_prefix + ":"
        self._prefix = key_prefix

    @classmethod
    def from_configs(
        cls,
        app: AppT,
        configs: dict[str, Any] | BaseModel,
        namespace: str = "cache",
    ) -> "RedisCacheBackend[AppT]":
        """
        Creates a backend from a config mapping or a CachingConfig
        (REDIS_URL, REDIS_PASSWORD, DURATION, KEY_PREFIX). KEY_PREFIX
        defaults to "patera:<application>:<namespace>:" (see
        default_key_prefix), so caches sharing a Redis database stay apart;
        set it to "" explicitly to use no namespace.
        """
        values = cls._config_values(configs)
        ttl = values.get("DURATION")
        key_prefix = values.get("KEY_PREFIX")
        return cls(
            url=values.get("REDIS_URL", ""),
            password=values.get("REDIS_PASSWORD", None),
            default_ttl=int(ttl) if ttl is not None else 300,
            key_prefix=(
                cls.default_key_prefix(app, namespace)
                if key_prefix is None
                else key_prefix
            ),
        )

    async def connect(self) -> None:
        if not self._client:
            # decode_responses=False -> bytes in/out
            self._client = await from_url(
                self._url,
                encoding="utf-8",
                decode_responses=False,
                password=self._password,
            )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ---- helpers ----
    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}" if self._prefix else key

    async def _ensure(self) -> Redis:
        if not self._client:
            # Allow lazy connect if caller forgot to call connect()
            await self.connect()
        assert self._client is not None
        return self._client

    async def get(self, key: str) -> Optional[dict]:
        client = await self._ensure()
        raw = await client.get(self._k(key))
        if not raw:
            return None
        # An entry that cannot be read (e.g. written by an older version)
        # counts as a miss and is replaced on the next set().
        return self.decode_payload(cast(bytes, raw))

    async def set(self, key: str, value: dict, duration: Optional[int] = None) -> None:
        client = await self._ensure()
        ttl = int(duration) if duration is not None else self.default_ttl
        if ttl <= 0:
            # Redis rejects non-positive expiry times; nothing to cache.
            await client.delete(self._k(key))
            return
        await client.set(self._k(key), self.encode_payload(value), ex=ttl)

    async def delete(
        self, key: str, *, regex: bool = False, wildcard: bool = False
    ) -> int:
        """
        Deletes entries (exact key, wildcard pattern or regex) in this
        backend's namespace and returns the number of deleted entries.
        """
        if regex and wildcard:
            raise ValueError("Use either regex=True or wildcard=True, not both.")

        client = await self._ensure()

        if not regex and not wildcard:
            return int(await client.delete(self._k(key)))

        if wildcard:
            matches = [k async for k in client.scan_iter(match=self._k(key))]
        else:
            pattern = re.compile(key)
            matches = []
            async for raw_key in client.scan_iter(match=f"{self._prefix}*"):
                text = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                if pattern.search(text[len(self._prefix) :]):
                    matches.append(raw_key)

        deleted = 0
        for i in range(0, len(matches), 1000):
            deleted += int(await client.delete(*matches[i : i + 1000]))
        return deleted

    async def clear(self) -> None:
        """
        Deletes every key under this backend's prefix. Without a prefix it
        raises RuntimeError rather than flushing the whole Redis database.
        """
        if not self._prefix:
            raise RuntimeError(
                "RedisCacheBackend has no key prefix, so clear() would delete "
                "every key in the Redis database. Set KEY_PREFIX (the default "
                "is 'patera:cache:'), or flush the database explicitly."
            )
        client = await self._ensure()
        keys: List[bytes] = []
        async for k in client.scan_iter(match=f"{self._prefix}*"):
            keys.append(k)
        # Delete in chunks to avoid huge payloads.
        for i in range(0, len(keys), 1000):
            await client.delete(*keys[i : i + 1000])
