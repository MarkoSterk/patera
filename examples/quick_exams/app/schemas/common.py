from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
)

EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
IMAGE_RE = re.compile(r"data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+")
MAX_IMAGE_LENGTH = 2_800_000
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL_RE.fullmatch(value):
        raise ValueError("Enter a valid email address")
    return value


def validate_image(value: str) -> str:
    if value and (len(value) > MAX_IMAGE_LENGTH or not IMAGE_RE.fullmatch(value)):
        raise ValueError("Use a PNG, JPEG, GIF or WebP image under 2 MB")
    return value


def sniff_image_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def image_data_url(content: bytes) -> str:
    """An uploaded image as the data URL questions store; the type is read from the bytes."""
    image_type = sniff_image_type(content)
    if image_type is None:
        raise ValueError("Use a PNG, JPEG, GIF or WebP image")
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("The image must be at most 2 MB")
    return f"data:{image_type};base64,{base64.b64encode(content).decode('ascii')}"


Email = Annotated[str, AfterValidator(normalize_email)]
Password = Annotated[str, Field(min_length=12, max_length=1024)]
Role = Literal["INSTRUCTOR", "ADMIN"]
AnswerIndex = Annotated[StrictInt, Field(ge=0, le=3)]
Points = Annotated[float, Field(gt=0, le=100_000, strict=True)]
Percentage = Annotated[float, Field(ge=0, le=100, strict=True)]


def _text(max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


Name = Annotated[str, _text(100)]
Title = Annotated[str, _text(200)]
Answer = Annotated[str, _text(2000)]
QuestionText = Annotated[str, _text(5000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
