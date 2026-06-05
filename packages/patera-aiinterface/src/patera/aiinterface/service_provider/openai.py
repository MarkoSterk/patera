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

from .chat_response import (
    ChatResponse,
    ChatMessage,
    UsageStats,
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
    async def chat(
        self,
        req: Request,
        system_prompt: str,
        user_prompt: str,
        use_history: bool,
        use_augmentation: bool,
        ext: AiService,
        **kwargs,
    ) -> ChatResponse:
        """
        Builds and sends chat prompt with chat service configs
        to the OpenAI Chat Completions API.
        """
        if (
            use_augmentation
            and hasattr(ext, "augmentation_provider")
            and ext.augmentation_provider is None
        ):
            raise ValueError(
                f"If you wish to use chat augmentation please implement the Augmentation Provider ({ext.__class__.__name__})"
            )

        if (
            use_history
            and hasattr(ext, "history_provider")
            and ext.history_provider is None
        ):
            raise ValueError(
                f"If you wish to use chat history please implement the History Provider ({ext.__class__.__name__})"
            )

        base_url = ext.configs.BASE_URL or "https://api.openai.com/v1"
        url = base_url.rstrip("/") + "/chat/completions"
        api_key = ext.configs.API_KEY
        if not api_key:
            raise ValueError(
                "API_KEY is required in AiServiceConfig for OpenAIServiceProvider."
            )

        msg: str = self.format_message(user_prompt, **kwargs)

        messages: list[dict[str, str]] = []
        if use_history:
            messages = await ext.history_provider.get_history_messages(req)  # type: ignore

        if use_augmentation:
            augmenting_info = await ext.augmentation_provider._augment_prompt(req, msg)  # type: ignore
            msg = msg + "\n\n----AUGMENTATION---:\n\n" + "\n\n".join(augmenting_info)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        if len(messages) == 0:
            sys_message = {"role": "system", "content": system_prompt}
            messages.append(sys_message)
            if use_history:
                ext.history_provider.save_message(sys_message, 0)  # type: ignore

        messages.append({"role": "user", "content": msg})

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

        if use_history:
            ext.history_provider.save_message(  # type: ignore
                messages[len(messages) - 1], len(messages) - 1
            )  # type: ignore

        openai_response = from_openai(json_response)

        if use_history:
            ext.history_provider.save_message(  # type: ignore
                openai_response.message.to_dict(), len(messages)
            )  # type: ignore

        return openai_response

    async def stream(
        self,
        req: Request,
        system_prompt: str,
        user_prompt: str,
        use_history: bool,
        use_augmentation: bool,
        ext: AiService,
        **kwargs,
    ) -> AsyncIterator[ChatResponse]:
        """
        Builds and sends chat prompt with chat service configs
        and yields a streaming response from the OpenAI Chat Completions API.
        """
        if (
            use_augmentation
            and hasattr(ext, "augmentation_provider")
            and ext.augmentation_provider is None
        ):
            raise ValueError(
                f"If you wish to use chat augmentation please implement the Augmentation Provider ({ext.__class__.__name__})"
            )

        if (
            use_history
            and hasattr(ext, "history_provider")
            and ext.history_provider is None
        ):
            raise ValueError(
                f"If you wish to use chat history please implement the History Provider ({ext.__class__.__name__})"
            )

        messages: list[dict[str, str]] = []
        if use_history:
            messages = await ext.history_provider.get_history_messages(req)  # type: ignore

        base_url = ext.configs.BASE_URL or "https://api.openai.com/v1"
        url = base_url.rstrip("/") + "/chat/completions"
        api_key = ext.configs.API_KEY

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        if not api_key:
            raise ValueError(f"API_KEY is required in for {ext.__class__.__name__}")

        msg: str = self.format_message(user_prompt, **kwargs)

        if use_augmentation:
            augmenting_info = await ext.augmentation_provider._augment_prompt(req, msg)  # type: ignore
            msg = msg + "\n\n----AUGMENTATION---:\n\n" + "\n\n".join(augmenting_info)

        if len(messages) == 0:
            sys_message = {"role": "system", "content": system_prompt}
            messages.append(sys_message)

            if use_history:
                ext.history_provider.save_message(sys_message, 0)  # type: ignore

        messages.append({"role": "user", "content": msg})

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

        if use_history:
            ext.history_provider.save_message(  # type: ignore
                messages[len(messages) - 1], len(messages) - 1
            )  # type: ignore

            ext.history_provider.save_message(  # type: ignore
                {
                    "role": "assistant",
                    "content": "".join(accumulated_content),
                },
                len(messages),
            )  # type: ignore

    def format_message(self, user_prompt: str, **kwargs) -> str:
        if kwargs:
            for key, value in kwargs.items():
                user_prompt = user_prompt.replace(f"<:{key}>", value)
        return user_prompt
