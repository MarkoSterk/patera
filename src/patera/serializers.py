from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import (
    Any,
    Optional,
    Protocol,
    Type,
    get_args,
    get_origin,
    runtime_checkable,
)

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
        return "".join(
            ndjson_line(item, response_type)
            for item in response.body  # type: ignore[union-attr]
        ).encode(charset)


def ndjson_line(item: Any, response_type: Optional[Type[Any]] = None) -> str:
    """
    Serializes one NDJSON record, terminated by a newline as the format
    requires. Dictionaries are validated through ``response_type`` when it
    is a Pydantic model, the same way JSON bodies are.
    """
    if isinstance(item, BaseModel):
        return item.model_dump_json() + "\n"
    # Response[list[Model]] or Response[AsyncIterator[Model]] describes rows.
    if get_origin(response_type) is not None:
        args = get_args(response_type)
        response_type = args[0] if len(args) == 1 else None
    if (
        response_type
        and isinstance(response_type, type)
        and issubclass(response_type, BaseModel)
        and isinstance(item, dict)
    ):
        return response_type(**item).model_dump_json() + "\n"
    return json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"


class SerializerRegistry:
    """
    Ordered list of response serializers. For each response, the first
    serializer whose ``can_serialize`` returns True renders the body.
    """

    def __init__(self) -> None:
        self._serializers: list[ResponseSerializer] = []

    @property
    def serializers(self) -> tuple[ResponseSerializer, ...]:
        """The registered serializers, in the order they are tried."""
        return tuple(self._serializers)

    def register(self, serializer: ResponseSerializer, *, first: bool = False) -> None:
        """
        Adds a serializer. By default it is tried after the ones already
        registered, so it only sees bodies no earlier serializer claims.
        With ``first=True`` it is tried before all of them, which is how a
        default is overridden, for example with a faster JSON encoder.
        """
        if first:
            self._serializers.insert(0, serializer)
        else:
            self._serializers.append(serializer)

    def replace(self, serializer_type: type, serializer: ResponseSerializer) -> None:
        """
        Puts ``serializer`` in the position of the registered serializer of
        type ``serializer_type``. Raises LookupError if there is none.
        """
        for index, registered in enumerate(self._serializers):
            if type(registered) is serializer_type:
                self._serializers[index] = serializer
                return
        raise LookupError(f"No serializer of type {serializer_type.__name__}.")

    def unregister(self, serializer_type: type) -> None:
        """Removes every registered serializer of type ``serializer_type``."""
        self._serializers = [
            s for s in self._serializers if type(s) is not serializer_type
        ]

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
