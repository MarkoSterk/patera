"""
Ai interface module
"""

from .ai_service import (
    AiService,
    ChatResponse,
    tool,
    system_prompt,
    user_prompt,
    history,
    augmentation,
    stream,
    session_id,
    AiServiceConfig,
)

__all__ = [
    "AiService",
    "ChatResponse",
    "tool",
    "AiServiceConfig",
    "system_prompt",
    "session_id",
    "user_prompt",
    "history",
    "augmentation",
    "stream",
]
