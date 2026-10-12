"""
Chat service provider
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from dataclasses import dataclass, asdict


Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str

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
    # ISO 8601 time at which the provider created the answer.
    created_at: str | None = None

    session_id: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "message": self.message.to_dict(),
            "finish_reason": self.finish_reason,
            "usage": self.usage.to_dict() if self.usage else None,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "session_id": self.session_id,
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
            session_id=data.get("session_id"),
        )


def iso_timestamp(value: Any) -> str | None:
    """A Unix timestamp (OpenAI) or an ISO string (Ollama) as ISO 8601 text."""
    if value is None or isinstance(value, str):
        return value
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
