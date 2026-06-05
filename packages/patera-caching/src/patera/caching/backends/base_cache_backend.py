"""
Base/Blueprint class for cache implementation
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Generic, Optional, Any, TypeVar
from patera import Patera
from ..cache import CachingConfig

AppT = TypeVar("AppT", bound=Patera[Any], default=Patera[Any])


class BaseCacheBackend(ABC, Generic[AppT]):
    """
    Abstract cache backend blueprint.

    Subclasses should implement:
    - configure_from_app(self, app, configs) -> None
    - connect / disconnect
    - get / set / delete / clear
    """

    @abstractmethod
    def configure_from_app(self, app: AppT, configs: CachingConfig) -> None:
        """Create a configured backend instance using app config."""

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
        """Delete cache entries."""

    @abstractmethod
    async def clear(self) -> None:
        """Clear the entire cache namespace."""
