"""
Ollama chat service provider
"""

from __future__ import annotations
import json
from typing import TYPE_CHECKING, Dict, Any
from collections.abc import AsyncIterator

if TYPE_CHECKING:
    from ..ai_service import AiServiceConfig

from .chat_response import (
    ChatResponse,
    ChatMessage,
    UsageStats,
)
from .base_service_provider import BaseServiceProvider


def from_ollama(data: dict[str, Any], session_id: Any = None) -> ChatResponse:
    message_data = data.get("message", {})

    return ChatResponse(
        provider="ollama",
        model=data.get("model", ""),
        message=ChatMessage(
            role=message_data.get("role", "assistant"),
            content=message_data.get("content", ""),
        ),
        finish_reason="stop" if data.get("done") else None,
        created_at=data.get("created_at"),
        usage=UsageStats(
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            total_tokens=(
                (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)
                if data.get("prompt_eval_count") is not None
                or data.get("eval_count") is not None
                else None
            ),
        ),
        session_id=session_id,
    )


class OllamaServiceProvider(BaseServiceProvider):
    """Ollama chat API (/api/chat)."""

    def _request(
        self, configs: AiServiceConfig, messages: list[ChatMessage], stream: bool
    ):
        url = configs.BASE_URL.rstrip("/") + "/api/chat"
        headers = {"Content-Type": "application/json"}
        if configs.API_KEY:
            headers["Authorization"] = f"Bearer {configs.API_KEY}"
        payload: Dict[str, Any] = {
            "model": configs.MODEL,
            "messages": self.message_dicts(messages),
            "stream": stream,
        }
        if configs.TEMPERATURE is not None:
            payload["options"] = {"temperature": configs.TEMPERATURE}
        response_format = configs.RESPONSE_FORMAT
        if response_format is not None:
            # Ollama takes "json" or a JSON schema in "format".
            if response_format.get("type") == "json_schema":
                payload["format"] = response_format.get("json_schema", {}).get(
                    "schema", {}
                )
            else:
                payload["format"] = "json"
        return url, headers, payload

    async def complete(
        self, messages: list[ChatMessage], configs: AiServiceConfig
    ) -> ChatResponse:
        url, headers, payload = self._request(configs, messages, stream=False)
        async with self.create_client(configs) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return from_ollama(response.json())

    async def stream(
        self, messages: list[ChatMessage], configs: AiServiceConfig
    ) -> AsyncIterator[ChatResponse]:
        """Yields the answer as it arrives (one JSON object per line)."""
        url, headers, payload = self._request(configs, messages, stream=True)
        async with self.create_client(configs) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        yield from_ollama(json.loads(line))
