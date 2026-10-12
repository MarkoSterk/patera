"""
AI interface for Patera applications (experimental).
"""

from .ai_service import (
    AiService,
    AiServiceConfig,
    HistorySummaryConfig,
    augmentation,
    history,
    system_prompt,
    user_prompt,
)
from .augmentation_provider.config import AugmentationConfig
from .history_provider import BaseHistoryProvider, HistorySummary, SqlHistoryProvider
from .service_provider import BaseServiceProvider, ChatMessage, ChatResponse

__all__ = [
    "AiService",
    "AiServiceConfig",
    "AugmentationConfig",
    "BaseHistoryProvider",
    "BaseServiceProvider",
    "ChatMessage",
    "ChatResponse",
    "HistorySummary",
    "HistorySummaryConfig",
    "SqlHistoryProvider",
    "augmentation",
    "history",
    "system_prompt",
    "user_prompt",
]
