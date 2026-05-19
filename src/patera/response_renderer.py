from __future__ import annotations

from typing import Any, Optional, Type, TYPE_CHECKING

from .http_statuses import HttpStatus
from .media_types import MediaType
from .response import Response
from .serializers import SerializerRegistry

if TYPE_CHECKING:
    from .patera import Patera  # noqa: F401


class ResponseRendererException(Exception):
    pass


class ResponseRenderer:
    """
    Finalizes non-streaming, non-zero-copy responses.
    """

    def __init__(self, serializers: SerializerRegistry, app: "Patera") -> None:
        self.serializers = serializers
        self._app = app

    async def render_body(
        self,
        response: Response[Any],
        response_type: Optional[Type[Any]] = None,
    ) -> bytes | None:
        """
        Applies default Content-Type inference and serializes the body.
        """
        try:
            self.apply_default_content_type(response)
            return await self.serializers.serialize(response, response_type)
        except Exception as e:
            self._app.logger.error(f"Error occurred while serializing response: {e}")
            raise ResponseRendererException("Failed to render response body") from e

    def apply_default_content_type(self, response: Response[Any]) -> None:
        """
        If the response does not already have a content-type header, infer it from body/media_type.
        """
        if "content-type" in response.headers:
            return

        if response.media_type is None:
            if response.is_streaming:
                response.media_type = MediaType.APPLICATION_OCTET_STREAM.value
            elif isinstance(response.body, str):
                response.media_type = MediaType.TEXT_PLAIN.value
                response.charset = response.charset or "utf-8"
            elif isinstance(response.body, (bytes, bytearray)):
                response.media_type = MediaType.APPLICATION_OCTET_STREAM.value
            elif response.body is not None:
                response.media_type = MediaType.APPLICATION_JSON.value
                response.charset = response.charset or "utf-8"

        if response.media_type is not None:
            content_type = response.media_type
            if self._should_append_charset(response.media_type, response.charset):
                content_type = f"{content_type}; charset={response.charset}"
            response.headers["content-type"] = content_type

    def finalize_headers(
        self,
        response: Response[Any],
        body_bytes: bytes | None,
        is_streaming: bool = False,
    ) -> None:
        """
        Applies final header rules like Content-Length and bodyless status handling.
        """
        status_code = int(response.status_code)

        if status_code in (int(HttpStatus.NO_CONTENT), 304):
            response.headers.pop("content-type", None)
            response.headers.pop("content-length", None)
            return

        if not is_streaming and body_bytes is not None:
            response.headers["content-length"] = str(len(body_bytes))
        elif is_streaming:
            response.headers.pop("content-length", None)

    @staticmethod
    def _should_append_charset(media_type: str, charset: str | None) -> bool:
        if not charset:
            return False

        return media_type.startswith("text/") or media_type in {
            MediaType.APPLICATION_JSON.value,
            MediaType.APPLICATION_PROBLEM_JSON.value,
            MediaType.APPLICATION_X_NDJSON.value,
            MediaType.APPLICATION_XML.value,
            MediaType.APPLICATION_YAML.value,
            MediaType.APPLICATION_GRAPHQL.value,
            MediaType.APPLICATION_CSV.value,
        }
