"""
Ollama chat service provider
"""

from __future__ import annotations
import json
from typing import TYPE_CHECKING, Dict, Any
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


class OllamaServiceProvider:
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

        url = ext.configs.BASE_URL
        url = url.rstrip("/") + "/api/chat"

        msg = self.format_message(user_prompt, **kwargs)

        messages: list[dict[str, str]] = []
        if use_history:
            messages = await ext.history_provider.get_history_messages(req)  # type: ignore

        if use_augmentation:
            augmenting_info = await ext.augmentation_provider._augment_prompt(req, msg)  # type: ignore
            msg = msg + "\n\n----AUGMENTATION---:\n\n" + "\n\n".join(augmenting_info)

        headers = {
            "Content-Type": "application/json",
        }

        if ext.configs.API_KEY:
            headers["Authorization"] = f"Bearer {ext.configs.API_KEY}"

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
            "options": {},
        }

        if ext.configs.TEMPERATURE is not None:
            payload["options"]["temperature"] = ext.configs.TEMPERATURE

        if not payload["options"]:
            payload.pop("options")

        timeout = ext.configs.TIMEOUT

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            json_response = response.json()

        if use_history:
            ext.history_provider.save_message(  # type: ignore
                messages[len(messages) - 1], len(messages) - 1
            )  # type: ignore

        ollama_response = from_ollama(json_response)
        if use_history:
            ext.history_provider.save_message(  # type: ignore
                ollama_response.message.to_dict(), len(messages)
            )  # type: ignore
        return ollama_response

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
        Builds and sends chat prompt with chat service configs and streaming response
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

        messages: list[Any] = []
        if use_history:
            messages = await ext.history_provider._get_history()  # type: ignore

        url = ext.configs.BASE_URL
        url = url.rstrip("/") + "/api/chat"
        headers = {
            "Content-Type": "application/json",
        }

        msg = self.format_message(user_prompt, **kwargs)

        if use_augmentation:
            augmenting_info = await ext.augmentation_provider._augment_prompt(req, msg)  # type: ignore
            msg = msg + "\n\n----AUGMENTATION---:\n\n" + "\n\n".join(augmenting_info)

        if ext.configs.API_KEY:
            headers["Authorization"] = f"Bearer {ext.configs.API_KEY}"

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
            "options": {},
        }

        if ext.configs.TEMPERATURE is not None:
            payload["options"]["temperature"] = ext.configs.TEMPERATURE

        if not payload["options"]:
            payload.pop("options")

        timeout = ext.configs.TIMEOUT

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield from_ollama(json.loads(line))

    def format_message(self, user_prompt: str, **kwargs) -> str:
        msg: str = ""
        if kwargs:
            for key, value in kwargs.items():
                msg = user_prompt.replace(f"<:{key}>", value)
        return msg
