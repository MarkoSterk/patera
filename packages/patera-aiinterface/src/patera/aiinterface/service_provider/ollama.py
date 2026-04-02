"""
Ollama chat service provider
"""

from __future__ import annotations
import json
from typing import TYPE_CHECKING, Dict, Any, Optional
from collections.abc import AsyncIterator
import httpx

if TYPE_CHECKING:
    from ..chat_service import AiService

from patera import Request

from .base_service_provider import (
    BaseServiceProvider,
    ChatResponse,
    ChatMessage,
    UsageStats,
)


def from_ollama(data: dict[str, Any]) -> ChatResponse:
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
    )


class OllamaServiceProvider(BaseServiceProvider):
    async def chat(self, req: Request, msg: str, ext: AiService) -> ChatResponse:
        """
        Builds and sends chat prompt with chat service configs
        """

        url = ext.configs.get("BASE_URL")
        if not url:
            raise ValueError(
                "BASE_URL is required in AiServiceConfig for OllamaServiceProvider."
            )

        url = url.rstrip("/") + "/api/chat"

        messages: list[dict[str, str]] = []
        session_id = req.route_parameters.get("session_id")
        if hasattr(ext, "history_provider") and ext.history_provider is not None:
            messages = await ext.history_provider._get_history_messages(session_id)  # type: ignore

        headers = {
            "Content-Type": "application/json",
        }

        if ext.configs.get("API_KEY"):
            headers["Authorization"] = f"Bearer {ext.configs['API_KEY']}"

        if len(messages) == 0:
            sys_prompt: Optional[str] = getattr(ext, "__system_prompt__", None)
            if sys_prompt is None:
                raise ValueError(
                    "System prompt is required for OllamaServiceProvider. Set it using the @system_prompt decorator on the chat service."
                )
            sys_message = {"role": "system", "content": sys_prompt}
            messages.append(sys_message)
            if hasattr(ext, "history_provider") and ext.history_provider is not None:
                ext.history_provider._save_message(sys_message, session_id, 0)  # type: ignore

        messages.append({"role": "user", "content": msg})

        payload: Dict[str, Any] = {
            "model": ext.configs["MODEL"],
            "messages": messages,
            "stream": False,
            "options": {},
        }

        if ext.configs.get("TEMPERATURE") is not None:
            payload["options"]["temperature"] = ext.configs["TEMPERATURE"]

        if not payload["options"]:
            payload.pop("options")

        timeout = ext.configs.get("TIMEOUT", 60)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            json_response = response.json()

        if hasattr(ext, "history_provider") and ext.history_provider is not None:
            ext.history_provider._save_message(
                messages[len(messages) - 1], session_id, len(messages) - 1
            )  # type: ignore

        ollama_response = from_ollama(json_response)
        if hasattr(ext, "history_provider") and ext.history_provider is not None:
            ext.history_provider._save_message(
                ollama_response.message.to_dict(), session_id, len(messages)
            )  # type: ignore
        return ollama_response

    async def stream(
        self, req: Request, msg: str, ext: AiService
    ) -> AsyncIterator[ChatResponse]:
        """
        Builds and sends chat prompt with chat service configs and streaming response
        """
        messages: list[Any] = []
        if ext.history_provider is not None:
            session_id = req.route_parameters.get("session_id")
            messages = await ext.history_provider._get_history(session_id)  # type: ignore

        url = ext.configs.get("API_URL")
        if not url:
            raise ValueError(
                "API_URL is required in AiConfig for OllamaServiceProvider."
            )

        headers = {
            "Content-Type": "application/json",
        }

        if ext.configs.get("API_KEY"):
            headers["Authorization"] = f"Bearer {ext.configs['API_KEY']}"

        if len(messages) == 0:
            messages = [
                {"role": "system", "content": ext.configs["SYSTEM_PROMPT"]},
            ]
        messages.append({"role": "user", "content": msg})

        payload: Dict[str, Any] = {
            "model": ext.configs["MODEL"],
            "messages": messages,
            "stream": True,
            "options": {},
        }

        if ext.configs.get("TEMPERATURE") is not None:
            payload["options"]["temperature"] = ext.configs["TEMPERATURE"]

        if not payload["options"]:
            payload.pop("options")

        timeout = ext.configs.get("TIMEOUT", 60)

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield from_ollama(json.loads(line))
