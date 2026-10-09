"""
Configuration model for the Caching extension.

Kept in its own module so that backends can import it without importing the
extension itself (which would be a circular import).
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CachingConfig(BaseModel):
    """Configuration model for Caching extension."""

    # Backend specific keys (e.g. REDIS_URL, SQLITE_PATH) are allowed.
    model_config = ConfigDict(extra="allow")

    DURATION: Optional[int] = Field(
        None, description="Default cache duration in seconds"
    )
    MAX_SIZE: Optional[int] = Field(
        None,
        description="Maximum number of items in the cache (if supported by backend)",
    )
