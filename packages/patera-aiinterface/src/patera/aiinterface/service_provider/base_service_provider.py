"""
Base class for chat service providers (OpenAI, Ollama, ...).

A provider only talks to the model: it sends a list of messages and turns the
answer into a ChatResponse. Building the messages (system prompt, history,
augmentation) and saving the history is the AiService's job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator

import httpx

from .chat_response import ChatMessage, ChatResponse

if TYPE_CHECKING:
    from ..ai_service import AiServiceConfig


class BaseServiceProvider(ABC):
    @abstractmethod
    async def complete(
        self, messages: list[ChatMessage], configs: "AiServiceConfig"
    ) -> ChatResponse:
        """Sends the messages and returns the whole answer."""

    def stream(
        self, messages: list[ChatMessage], configs: "AiServiceConfig"
    ) -> AsyncIterator[ChatResponse]:
        """
        Sends the messages and yields the answer in parts. Implementations are
        async generators (``async def stream(...): ... yield chunk``).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support streaming; implement stream()."
        )

    @staticmethod
    def message_dicts(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Messages in the role/content form both APIs accept."""
        return [{"role": m.role, "content": m.content} for m in messages]

    @staticmethod
    def create_client(configs: "AiServiceConfig") -> httpx.AsyncClient:
        """HTTP client with TIMEOUT; MAX_RETRIES retries failed connections."""
        return httpx.AsyncClient(
            timeout=configs.TIMEOUT,
            transport=httpx.AsyncHTTPTransport(retries=configs.MAX_RETRIES),
        )
