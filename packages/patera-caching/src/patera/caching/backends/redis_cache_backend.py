"""
Redis cache implementation

CACHE_REDIS_URL       = "redis://localhost:6379/0"   # required
CACHE_REDIS_PASSWORD  = None                          # optional
CACHE_DURATION        = 300                           # optional (default TTL)
CACHE_KEY_PREFIX      = "patera:cache:"              # optional prefix/namespace
"""

from __future__ import annotations

import pickle
import re
from typing import Generic, Optional, TypeVar, cast, List, TYPE_CHECKING, Any

from pydantic import BaseModel
from redis.asyncio import Redis, from_url

from .base_cache_backend import BaseCacheBackend

if TYPE_CHECKING:
    from patera import Patera

AppT = TypeVar("AppT", bound="Patera", default="Patera")


class RedisCacheBackend(BaseCacheBackend[AppT], Generic[AppT]):
    """Redis-backed cache using binary pickled payloads."""

    def __init__(
        self,
        url: str,
        password: Optional[str] = None,
        default_ttl: int = 300,
        key_prefix: str = "",
    ) -> None:
        if not url:
            raise ValueError("CACHE_REDIS_URL must be set for RedisCacheBackend")
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
    def configure_from_app(  # type: ignore[override]
        cls, app: AppT, configs: dict[str, Any] | BaseModel
    ) -> "RedisCacheBackend":
        """
        Creates a backend from a config mapping or a CachingConfig
        (REDIS_URL, REDIS_PASSWORD, DURATION, KEY_PREFIX).
        """
        if isinstance(configs, BaseModel):
            configs = configs.model_dump()
        url = configs.get("REDIS_URL", "")
        password = configs.get("REDIS_PASSWORD", None)
        ttl = configs.get("DURATION")
        key_prefix = configs.get("KEY_PREFIX", "") or ""
        return cls(
            url=url,
            password=password,
            default_ttl=int(ttl) if ttl is not None else 300,
            key_prefix=key_prefix,
        )

    async def connect(self) -> None:
        if not self._client:
            # decode_responses=False -> bytes in/out, good for pickled values
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
        return cast(dict, pickle.loads(cast(bytes, raw)))

    async def set(self, key: str, value: dict, duration: Optional[int] = None) -> None:
        client = await self._ensure()
        ttl = int(duration) if duration is not None else self.default_ttl
        if ttl <= 0:
            # Redis rejects non-positive expiry times; nothing to cache.
            await client.delete(self._k(key))
            return
        await client.set(self._k(key), pickle.dumps(value), ex=ttl)

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
        client = await self._ensure()
        if self._prefix and self._prefix != "":
            keys: List[bytes] = []
            async for k in client.scan_iter(match=f"{self._prefix}*"):
                keys.append(k)
            if keys:
                # Pipeline deletion in chunks to avoid huge payloads
                # pylint: disable-next=C0103
                CHUNK = 1000
                for i in range(0, len(keys), CHUNK):
                    chunk = keys[i : i + CHUNK]
                    await client.delete(*chunk)
        else:
            # flushes entire Redis db in case no namespace prefix is configured
            await client.flushdb()
