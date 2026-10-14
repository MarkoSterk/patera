from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import (
    Any,
    Optional,
    Protocol,
    Type,
    get_args,
    get_origin,
    runtime_checkable,
)

from pydantic import BaseModel, TypeAdapter
from pydantic_core import to_json

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
        return _encode(json_bytes(response.body, response_type), charset)


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


def _mentions_model(response_type: Any) -> bool:
    """True for a Pydantic model, or a type built from one (list[Model], ...)."""
    if isinstance(response_type, type) and issubclass(response_type, BaseModel):
        return True
    return any(_mentions_model(arg) for arg in get_args(response_type))


@lru_cache(maxsize=512)
def _adapter(response_type: Any) -> TypeAdapter[Any]:
    return TypeAdapter(response_type)


def json_bytes(value: Any, response_type: Any = None) -> bytes:
    """
    The JSON encoding of a response body, as UTF-8.

    When the declared response type involves a Pydantic model, such as
    ``PostOut``, ``list[PostOut]`` or ``dict[str, PostOut]``, the body is
    validated through it first: fields the model does not declare are left
    out, and dictionaries, model instances and objects with matching
    attributes are all accepted. Otherwise the value is encoded as it is.
    Either way, models, dates, times, UUIDs, decimals, enums and sets are
    encoded the way Pydantic encodes them.
    """
    if response_type is not None and _mentions_model(response_type):
        try:
            adapter = _adapter(response_type)
        except TypeError:  # an unhashable annotation: build the adapter each time
            adapter = TypeAdapter(response_type)
        return adapter.dump_json(adapter.validate_python(value, from_attributes=True))
    return to_json(value)


def _encode(data: bytes, charset: str) -> bytes:
    if charset.replace("-", "").lower() == "utf8":
        return data
    return data.decode("utf-8").encode(charset)


def ndjson_line(item: Any, response_type: Optional[Type[Any]] = None) -> str:
    """
    Serializes one NDJSON record, terminated by a newline as the format
    requires. Records are validated through the declared row type, the same
    way JSON bodies are: ``Response[list[Model]]`` and
    ``Response[AsyncIterator[Model]]`` describe rows of ``Model``.
    """
    if get_origin(response_type) is not None:
        args = get_args(response_type)
        response_type = args[0] if len(args) == 1 else None
    return json_bytes(item, response_type).decode("utf-8") + "\n"


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
