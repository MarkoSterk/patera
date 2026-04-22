from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable, Type

from pydantic import BaseModel

from .http_statuses import HttpStatus
from .media_types import MediaType
from .response import Response


@runtime_checkable
class ResponseSerializer(Protocol):
    def can_serialize(self, response: Response[Any]) -> bool: ...

    async def serialize(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None: ...


@dataclass(slots=True)
class NoContentSerializer:
    BODYLESS_STATUS_CODES: tuple[int, ...] = (
        int(HttpStatus.NO_CONTENT),
        304,
    )

    def can_serialize(self, response: Response[Any]) -> bool:
        return int(response.status_code) in self.BODYLESS_STATUS_CODES

    async def serialize(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None:
        response.body = None
        return None


@dataclass(slots=True)
class BytesSerializer:
    def can_serialize(self, response: Response[Any]) -> bool:
        return isinstance(response.body, (bytes, bytearray))

    async def serialize(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None:
        return bytes(response.body)  # type: ignore


@dataclass(slots=True)
class StringSerializer:
    DEFAULT_CHARSET: str = "utf-8"

    def can_serialize(self, response: Response[Any]) -> bool:
        return isinstance(response.body, str)

    async def serialize(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None:
        charset = response.charset or self.DEFAULT_CHARSET
        return response.body.encode(charset)  # type: ignore


@dataclass(slots=True)
class JsonSerializer:
    JSON_MEDIA_TYPES: tuple[str, ...] = (
        MediaType.APPLICATION_JSON.value,
        MediaType.APPLICATION_PROBLEM_JSON.value,
    )
    DEFAULT_CHARSET: str = "utf-8"

    def can_serialize(self, response: Response[Any]) -> bool:
        return (
            response.body is not None
            and response.media_type in self.JSON_MEDIA_TYPES
            and not isinstance(response.body, (bytes, bytearray, str))
        )

    async def serialize(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None:
        charset = response.charset or self.DEFAULT_CHARSET
        body = response.body

        if (
            response_type
            and isinstance(response_type, type)
            and issubclass(response_type, BaseModel)
            and isinstance(body, dict)
        ):
            model_instance = response_type(**body)
            return model_instance.model_dump_json().encode(charset)

        if isinstance(body, BaseModel):
            return body.model_dump_json().encode(charset)

        return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
            charset
        )


@dataclass(slots=True)
class NdjsonSerializer:
    DEFAULT_CHARSET: str = "utf-8"

    def can_serialize(self, response: Response[Any]) -> bool:
        return (
            response.media_type == MediaType.APPLICATION_X_NDJSON.value
            and response.body is not None
            and isinstance(response.body, Iterable)
            and not isinstance(response.body, (str, bytes, bytearray, dict))
        )

    async def serialize(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None:
        charset = response.charset or self.DEFAULT_CHARSET

        lines: list[str] = []
        for item in response.body:  # type: ignore
            if isinstance(item, BaseModel):
                lines.append(item.model_dump_json())
            elif (
                response_type
                and isinstance(response_type, type)
                and issubclass(response_type, BaseModel)
                and isinstance(item, dict)
            ):
                model_instance = response_type(**item)
                lines.append(model_instance.model_dump_json())
            else:
                lines.append(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                )

        return "\n".join(lines).encode(charset)


class SerializerRegistry:
    def __init__(self) -> None:
        self._serializers: list[ResponseSerializer] = []

    def register(self, serializer: ResponseSerializer) -> None:
        self._serializers.append(serializer)

    def register_defaults(self) -> None:
        self.register(NoContentSerializer())
        self.register(BytesSerializer())
        self.register(JsonSerializer())
        self.register(NdjsonSerializer())
        self.register(StringSerializer())

    async def serialize(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None:
        for serializer in self._serializers:
            if serializer.can_serialize(response):
                return await serializer.serialize(response, response_type)

        if response.body is None:
            return None

        raise TypeError(
            "No serializer found for response body type "
            f"{type(response.body)!r} and media type {response.media_type!r}."
        )
