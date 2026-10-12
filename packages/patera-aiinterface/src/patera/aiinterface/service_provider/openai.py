"""
OpenAI chat service provider
"""

from __future__ import annotations
import json
from typing import TYPE_CHECKING, Dict, Any, Optional
from collections.abc import AsyncIterator

if TYPE_CHECKING:
    from ..ai_service import AiServiceConfig

from .chat_response import (
    ChatResponse,
    ChatMessage,
    UsageStats,
    iso_timestamp,
)
from .base_service_provider import BaseServiceProvider


def from_openai(data: dict[str, Any]) -> ChatResponse:
    """
    Convert a non-stream OpenAI Chat Completions response
    into the internal ChatResponse format.
    """
    choices = data.get("choices", [])
    first_choice = choices[0] if choices else {}
    message_data = first_choice.get("message", {}) or {}
    usage = data.get("usage", {}) or {}

    return ChatResponse(
        provider="openai",
        model=data.get("model", ""),
        message=ChatMessage(
            role=message_data.get("role", "assistant"),
            content=message_data.get("content", "") or "",
        ),
        finish_reason=first_choice.get("finish_reason"),
        request_id=data.get("id"),
        created_at=iso_timestamp(data.get("created")),
        usage=UsageStats(
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        ),
    )


def from_openai_chunk(data: dict[str, Any]) -> Optional[ChatResponse]:
    """
    Convert a streamed OpenAI Chat Completions chunk
    into the internal ChatResponse format.
    Returns None for empty chunks that carry no delta content
    and no finish reason.
    """
    choices = data.get("choices", [])
    first_choice = choices[0] if choices else {}
    delta = first_choice.get("delta", {}) or {}
    usage = data.get("usage", {}) or {}

    content = delta.get("content")
    finish_reason = first_choice.get("finish_reason")

    if content is None and finish_reason is None and not usage:
        return None

    return ChatResponse(
        provider="openai",
        model=data.get("model", ""),
        message=ChatMessage(
            role=delta.get("role", "assistant"),
            content=content or "",
        ),
        finish_reason=finish_reason,
        request_id=data.get("id"),
        created_at=iso_timestamp(data.get("created")),
        usage=UsageStats(
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        ),
    )


class OpenAIServiceProvider(BaseServiceProvider):
    """OpenAI Chat Completions API (and compatible servers)."""

    def _request(
        self, configs: AiServiceConfig, messages: list[ChatMessage], stream: bool
    ):
        if not configs.API_KEY:
            raise ValueError("API_KEY is required for the OpenAI service provider.")
        url = configs.BASE_URL.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {configs.API_KEY}",
        }
        if configs.ORGANIZATION_ID:
            headers["OpenAI-Organization"] = configs.ORGANIZATION_ID
        if configs.PROJECT_ID:
            headers["OpenAI-Project"] = configs.PROJECT_ID
        payload: Dict[str, Any] = {
            "model": configs.MODEL,
            "messages": self.message_dicts(messages),
            "stream": stream,
        }
        if configs.TEMPERATURE is not None:
            payload["temperature"] = configs.TEMPERATURE
        if configs.RESPONSE_FORMAT is not None:
            payload["response_format"] = configs.RESPONSE_FORMAT
        if stream:
            # The last chunk then carries the token usage.
            payload["stream_options"] = {"include_usage": True}
        return url, headers, payload

    async def complete(
        self, messages: list[ChatMessage], configs: AiServiceConfig
    ) -> ChatResponse:
        url, headers, payload = self._request(configs, messages, stream=False)
        async with self.create_client(configs) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return from_openai(response.json())

    async def stream(
        self, messages: list[ChatMessage], configs: AiServiceConfig
    ) -> AsyncIterator[ChatResponse]:
        """Yields the answer as it arrives (server-sent events)."""
        url, headers, payload = self._request(configs, messages, stream=True)
        async with self.create_client(configs) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    # Lines look like "data: {...}"; the last one is "data: [DONE]".
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    chunk = from_openai_chunk(json.loads(data))
                    if chunk is not None:
                        yield chunk
