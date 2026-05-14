"""
Chat service provider
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Literal, TypeVar
from dataclasses import dataclass, asdict
from patera import Request
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

if TYPE_CHECKING:
    from ..ai_service import AiService

Role = Literal["system", "user", "assistant", "tool"]

T = TypeVar("T")


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str
    thinking: str | None = None
    name: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatMessage:
        return cls(**data)


@dataclass(slots=True)
class UsageStats:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageStats:
        return cls(**data)


@dataclass(slots=True)
class ChatResponse:
    provider: str
    model: str
    message: ChatMessage
    finish_reason: str | None = None
    usage: UsageStats | None = None

    request_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "message": self.message.to_dict(),
            "finish_reason": self.finish_reason,
            "usage": self.usage.to_dict() if self.usage else None,
            "request_id": self.request_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatResponse:
        return cls(
            provider=data["provider"],
            model=data["model"],
            message=ChatMessage.from_dict(data["message"]),
            finish_reason=data.get("finish_reason"),
            usage=UsageStats.from_dict(data["usage"]) if data.get("usage") else None,
            request_id=data.get("request_id"),
            created_at=data.get("created_at"),
        )


class BaseServiceProvider(ABC):
    @abstractmethod
    async def chat(self, req: Request, system_prompt: str,
                   user_prompt: str, use_history: bool,
                   use_augmentation: bool,
                   ext: AiService, **kwargs) -> ChatResponse: ...

    def stream(elf, req: Request, system_prompt: str,
                user_prompt: str, use_history: bool,
                use_augmentation: bool,
                ext: AiService) -> AsyncIterator[ChatResponse]:
        raise NotImplementedError("If you wish to use streaming implement this method")
