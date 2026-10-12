"""
Base/Blueprint class for cache implementation
"""

from __future__ import annotations
import re
from abc import ABC, abstractmethod
from typing import Generic, Optional, Any, Self, TypeVar
from pydantic import BaseModel

from patera import Patera
from ..config import CachingConfig

AppT = TypeVar("AppT", bound=Patera[Any], default=Patera[Any])


class BaseCacheBackend(ABC, Generic[AppT]):
    """
    Abstract cache backend blueprint.

    Subclasses implement:
    - from_configs(cls, app, configs, namespace) -> backend   (a classmethod)
    - connect / disconnect
    - get / set / delete / clear

    Every backend is created the same way: either directly with its
    constructor, or with ``from_configs`` from the Caching extension's
    configuration, which is what the extension does for its
    ``backend_class``.
    """

    @classmethod
    def from_configs(
        cls,
        app: AppT,
        configs: CachingConfig | BaseModel | dict[str, Any],
        namespace: str = "cache",
    ) -> Self:
        """
        Creates a backend configured from the Caching extension's settings.
        ``namespace`` names the cache (the Caching extension passes its
        configuration name, e.g. "public_cache"); shared stores use it for
        their default key prefix. The default calls the constructor without
        arguments; backends with settings override it.
        """
        return cls()

    @staticmethod
    def default_key_prefix(app: Optional[AppT], namespace: str = "cache") -> str:
        """
        Key prefix for a shared store (Redis, an SQLite file):
        "patera:<application>:<namespace>:", for example
        "patera:blog:public_cache:". Two caches, or two applications, using
        the same store then never share keys, and clear() on one leaves the
        others alone.
        """

        def slug(text: str) -> str:
            return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

        parts = ["patera"]
        app_name = getattr(app, "app_name", None) if app is not None else None
        if app_name and slug(str(app_name)):
            parts.append(slug(str(app_name)))
        parts.append(slug(namespace) or "cache")
        return ":".join(parts) + ":"

    @staticmethod
    def _config_values(
        configs: CachingConfig | BaseModel | dict[str, Any],
    ) -> dict[str, Any]:
        """Returns the configuration, including extra keys, as a dictionary."""
        if isinstance(configs, BaseModel):
            return configs.model_dump()
        return dict(configs)

    @abstractmethod
    async def connect(self) -> None:
        """Establish any required connections (no-op for memory)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down connections (no-op for memory)."""

    @abstractmethod
    async def get(self, key: str) -> Optional[dict]:
        """Return cached payload dict or None."""

    @abstractmethod
    async def set(self, key: str, value: dict, duration: Optional[int] = None) -> None:
        """Store payload dict under key with optional TTL in seconds."""

    @abstractmethod
    async def delete(
        self, key: str, *, regex: bool = False, wildcard: bool = False
    ) -> int:
        """
        Delete cache entries and return the number of deleted entries.

        - exact key by default
        - wildcard=True: shell-style pattern (fnmatch), e.g. "users:*"
        - regex=True: regular expression searched in the key
        """

    @abstractmethod
    async def clear(self) -> None:
        """Clear the entire cache namespace."""
