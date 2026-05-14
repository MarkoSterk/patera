"""
OpenAI chat service provider
"""

from __future__ import annotations
import json
from typing import TYPE_CHECKING, Dict, Any, Optional
from collections.abc import AsyncIterator
import httpx

if TYPE_CHECKING:
    from ..ai_service import AiService

from patera import Request

from .base_service_provider import (
    BaseServiceProvider,
    ChatResponse,
    ChatMessage,
    UsageStats,
)


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
        created_at=data.get("created"),
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
        created_at=data.get("created"),
        usage=UsageStats(
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        ),
    )


class OpenAIServiceProvider(BaseServiceProvider):
    async def chat(self, req: Request, system_prompt: str,
                   user_prompt: str, use_history: bool,
                   use_augmentation: bool,
                   ext: AiService, **kwargs) -> ChatResponse:
        """
        Builds and sends chat prompt with chat service configs
        to the OpenAI Chat Completions API.
        """
        base_url = ext.configs.BASE_URL or "https://api.openai.com/v1"
        api_key = ext.configs.API_KEY

        if not api_key:
            raise ValueError(
                "API_KEY is required in AiServiceConfig for OpenAIServiceProvider."
            )

        url = base_url.rstrip("/") + "/chat/completions"

        msg: str = ""
        if kwargs:
            for key, value in kwargs.items():
                msg = user_prompt.replace(f"<:{key}>", value)

        messages: list[dict[str, str]] = []
        session_id = req.route_parameters.get("session_id", None)

        if use_history and hasattr(ext, "history_provider") and ext.history_provider is not None:
            messages = await ext.history_provider.get_history_messages(req)  # type: ignore

        if (use_augmentation and 
            hasattr(ext, "augmentation_provider")
            and ext.augmentation_provider is not None
        ):
            augmenting_info = await ext.augmentation_provider._augment_prompt(req, msg)
            if augmenting_info:
                msg = (
                    msg
                    + "\n\n----AUGMENTATION---:\n\n"
                    + "\n\n".join(augmenting_info)
                )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        if len(messages) == 0:
            sys_message = {"role": "system", "content": system_prompt}
            messages.append(sys_message)

            if use_history and hasattr(ext, "history_provider") and ext.history_provider is not None:
                ext.history_provider.save_message(sys_message, session_id, 0)  # type: ignore

        user_message = {"role": "user", "content": msg}
        messages.append(user_message)

        payload: Dict[str, Any] = {
            "model": ext.configs.MODEL,
            "messages": messages,
            "stream": False,
        }

        if ext.configs.TEMPERATURE is not None:
            payload["temperature"] = ext.configs.TEMPERATURE

        timeout = ext.configs.TIMEOUT

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            json_response = response.json()

        if use_history and hasattr(ext, "history_provider") and ext.history_provider is not None:
            ext.history_provider.save_message(
                user_message, session_id, len(messages) - 1
            )  # type: ignore

        openai_response = from_openai(json_response)

        if use_history and hasattr(ext, "history_provider") and ext.history_provider is not None:
            ext.history_provider.save_message(
                openai_response.message.to_dict(), session_id, len(messages)
            )  # type: ignore

        return openai_response

    async def stream(
        self, req: Request, msg: str, ext: AiService
    ) -> AsyncIterator[ChatResponse]:
        """
        Builds and sends chat prompt with chat service configs
        and yields a streaming response from the OpenAI Chat Completions API.
        """
        messages: list[dict[str, str]] = []
        session_id = req.route_parameters.get("session_id", None)

        if hasattr(ext, "history_provider") and ext.history_provider is not None:
            messages = await ext.history_provider.get_history_messages(req)  # type: ignore

        if (
            hasattr(ext, "augmentation_provider")
            and ext.augmentation_provider is not None
        ):
            augmenting_info = await ext.augmentation_provider._augment_prompt(req, msg)
            if augmenting_info:
                msg = (
                    msg
                    + "\n\nAdditional Information:\n\n"
                    + "\n\n".join(augmenting_info)
                )

        base_url = ext.configs.BASE_URL or "https://api.openai.com/v1"
        api_key = ext.configs.API_KEY

        if not api_key:
            raise ValueError(
                "API_KEY is required in AiServiceConfig for OpenAIServiceProvider."
            )

        url = base_url.rstrip("/") + "/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        if len(messages) == 0:
            sys_prompt: Optional[str] = getattr(ext, "__system_prompt__", None)
            if sys_prompt is None:
                raise ValueError(
                    "System prompt is required for OpenAIServiceProvider. "
                    "Set it using the @system_prompt decorator on the chat service "
                    "or provide SYSTEM_PROMPT in configs."
                )

            sys_message = {"role": "system", "content": sys_prompt}
            messages.append(sys_message)

            if hasattr(ext, "history_provider") and ext.history_provider is not None:
                ext.history_provider.save_message(sys_message, session_id, 0)  # type: ignore

        user_message = {"role": "user", "content": msg}
        messages.append(user_message)

        payload: Dict[str, Any] = {
            "model": ext.configs.MODEL,
            "messages": messages,
            "stream": True,
        }

        if ext.configs.TEMPERATURE is not None:
            payload["temperature"] = ext.configs.TEMPERATURE

        # For final usage in stream
        payload["stream_options"] = {"include_usage": True}

        timeout = ext.configs.TIMEOUT
        accumulated_content: list[str] = []

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # OpenAI streaming uses SSE lines like: "data: {...}"
                    if not line.startswith("data:"):
                        continue

                    data_str = line[len("data:") :].strip()

                    if data_str == "[DONE]":
                        break

                    chunk_json = json.loads(data_str)
                    chunk_response = from_openai_chunk(chunk_json)

                    if chunk_response is None:
                        continue

                    if chunk_response.message.content:
                        accumulated_content.append(chunk_response.message.content)

                    yield chunk_response

        if hasattr(ext, "history_provider") and ext.history_provider is not None:
            ext.history_provider.save_message(
                user_message, session_id, len(messages) - 1
            )  # type: ignore

            ext.history_provider.save_message(
                {
                    "role": "assistant",
                    "content": "".join(accumulated_content),
                },
                session_id,
                len(messages),
            )  # type: ignore
