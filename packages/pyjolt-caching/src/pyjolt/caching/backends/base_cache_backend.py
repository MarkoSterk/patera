"""
Base/Blueprint class for cache implementation
"""

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyjolt import PyJolt


class BaseCacheBackend(ABC):
    """
    Abstract cache backend blueprint.

    Subclasses should implement:
    - configure_from_app(cls, app) -> BaseCacheBackend
    - connect / disconnect
    - get / set / delete / clear
    """

    @classmethod
    @abstractmethod
    def configure_from_app(
        cls, app: "PyJolt", configs: dict[str, Any]
    ) -> "BaseCacheBackend":
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
    async def delete(self, key: str) -> None:
        """Delete a cached entry if present."""

    @abstractmethod
    async def clear(self) -> None:
        """Clear the entire cache namespace."""
