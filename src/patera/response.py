"""
Response class. Holds all information regarding responses to individual requests.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from typing import (
    Any,
    Optional,
    TYPE_CHECKING,
    Self,
    TypeVar,
    Generic,
    Type,
    cast,
    AsyncIterator,
)

from .media_types import MediaType
from .utilities import run_sync_or_async
from .http_statuses import HttpStatus

if TYPE_CHECKING:
    from .patera import Patera
    from .request import Request

U = TypeVar("U")


class Response(Generic[U]):
    """
    Response object of the application. Holds status code, headers, body, stream and rendering metadata.

    Example:
    ```python
    return res.json({"message": "OK"}).status(HttpStatus.OK)
    ```
    """

    def __init__(self, app: "Patera[Any]", request: "Request") -> None:
        self._app = app
        self._request = request

        self.status_code: int | HttpStatus = HttpStatus.OK
        self.headers: dict[str, str] = {}
        self.body: Optional[U] = None

        self.media_type: Optional[str] = None
        self.charset: Optional[str] = None

        self.render_engine = self._app.jinja_environment
        self._zero_copy: Any = None
        self._expected_body_type: Optional[Type[Any]] = None

        self._stream: Optional[AsyncIterable[bytes] | Iterable[bytes]] = None

        # Cookies are kept separately so each one can be emitted as its own Set-Cookie header.
        self._cookies: list[str] = []

    def status(self, status_code: int | HttpStatus) -> Self:
        """
        Sets the response status code.
        """
        self.status_code = status_code
        return self

    def redirect(
        self,
        location: str,
        status_code: int | HttpStatus = HttpStatus.SEE_OTHER,
    ) -> Self:
        """
        Redirects the client to the provided location.
        """
        self.set_header("location", location)
        self.status_code = status_code
        self.body = None
        self.media_type = None
        self.charset = None
        return self

    def no_content(self) -> Self:
        """
        Creates a 204 No Content response.
        """
        self.body = None
        self.media_type = None
        self.charset = None
        self.status(HttpStatus.NO_CONTENT)
        return self

    def json(self, data: Any) -> Self:
        """
        Creates a JSON response. Actual JSON serialization is done later by a serializer.
        """
        self.body = cast(U, data)
        self.media_type = MediaType.APPLICATION_JSON.value
        self.charset = "utf-8"
        return self

    def problem(
        self,
        title: str,
        detail: str,
        status: int | HttpStatus,
        type_: str = "about:blank",
        instance: str | None = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> Self:
        """
        Creates an RFC 7807 / RFC 9457 style problem response.
        """
        payload: dict[str, Any] = {
            "type": type_,
            "title": title,
            "status": int(status),
            "detail": detail,
        }

        if instance is not None:
            payload["instance"] = instance

        if extra:
            payload.update(extra)

        self.body = cast(U, payload)
        self.media_type = MediaType.APPLICATION_PROBLEM_JSON.value
        self.charset = "utf-8"
        self.status(status)
        return self

    def text(self, text: str) -> Self:
        """
        Creates a plain text response. Encoding is done later by a serializer.
        """
        self.body = cast(U, text)
        self.media_type = MediaType.TEXT_PLAIN.value
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    def html_body(self, html: str) -> Self:
        """
        Creates an HTML response from an already-rendered HTML string.
        """
        self.body = cast(U, html)
        self.media_type = MediaType.TEXT_HTML.value
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    def xml(self, xml: str, media_type: str = MediaType.APPLICATION_XML.value) -> Self:
        """
        Creates an XML response.
        """
        self.body = cast(U, xml)
        self.media_type = media_type
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    def csv(self, csv_text: str, media_type: str = MediaType.TEXT_CSV.value) -> Self:
        """
        Creates a CSV response.
        """
        self.body = cast(U, csv_text)
        self.media_type = media_type
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    def yaml(
        self,
        yaml_text: str,
        media_type: str = MediaType.TEXT_YAML.value,
    ) -> Self:
        """
        Creates a YAML response.
        """
        self.body = cast(U, yaml_text)
        self.media_type = media_type
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    def ndjson(self, rows: Any) -> Self:
        """
        Creates an NDJSON response. The body is expected to be an iterable of JSON-serializable items.
        Serialization is done later by a serializer.
        """
        self.body = cast(U, rows)
        self.media_type = MediaType.APPLICATION_X_NDJSON.value
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    def bytes(
        self,
        data: bytes | bytearray,
        media_type: str = MediaType.APPLICATION_OCTET_STREAM.value,
    ) -> Self:
        """
        Creates a binary response.
        """
        self.body = cast(U, bytes(data))
        self.media_type = media_type
        self.charset = None
        self.status(HttpStatus.OK)
        return self

    async def html_from_string(
        self,
        text: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Self:
        """
        Renders an HTML string as a Jinja template and stores the rendered HTML as response body.
        """
        if context is None:
            context = {}

        for method in self.app.global_context_methods:
            additional_context = await run_sync_or_async(method)
            if not isinstance(additional_context, dict):
                raise ValueError(
                    "Return of global context method must be of type dictionary."
                )
            context.update(additional_context)

        context["app"] = self.app
        context["url_for"] = self.app.url_for
        context["request"] = self._request
        context["attribute"] = getattr
        context["len"] = len

        rendered = await self.render_engine.from_string(text).render_async(**context)

        self.body = cast(U, rendered)
        self.media_type = MediaType.TEXT_HTML.value
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    async def html(
        self,
        template_path: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Self:
        """
        Renders an HTML template and stores the rendered HTML as response body.

        template_path: relative path of template inside the templates folder
        context: dictionary with data used in the template
        """
        if context is None:
            context = {}

        for method in self.app.global_context_methods:
            additional_context = await run_sync_or_async(method)
            if not isinstance(additional_context, dict):
                raise ValueError(
                    "Return of global context method must be of type dictionary."
                )
            context = {**context, **additional_context}

        context["app"] = self.app
        context["url_for"] = self.app.url_for
        context["request"] = self._request
        context["attribute"] = getattr
        context["len"] = len

        template = self.render_engine.get_template(template_path)
        rendered = await template.render_async(**context)

        self.body = cast(U, rendered)
        self.media_type = MediaType.TEXT_HTML.value
        self.charset = "utf-8"
        self.status(HttpStatus.OK)
        return self

    def send_file(self, body: bytes | bytearray, headers: dict[str, str]) -> Self:
        """
        Creates a file response. The caller can pass precomputed headers such as Content-Disposition.

        If Content-Type is present in headers, it is mirrored into response.media_type.
        """
        for key, value in headers.items():
            self.set_header(key, value)

        self.body = cast(U, bytes(body))

        header_content_type = self.headers.get("content-type")
        if header_content_type:
            self.media_type = header_content_type.split(";", 1)[0].strip()

        return self

    def set_header(self, key: str, value: str) -> Self:
        """
        Sets or updates a normal header in the response.

        Note:
        - Set-Cookie must be handled through set_cookie() or delete_cookie().
        """
        normalized = key.lower()
        if normalized == "set-cookie":
            raise ValueError(
                "Use set_cookie() or delete_cookie() instead of set_header('Set-Cookie', ...)."
            )

        self.headers[normalized] = value

        if normalized == "content-type":
            media_type, charset = self._parse_content_type(value)
            self.media_type = media_type
            self.charset = charset

        return self

    def set_headers(self, headers: dict[str, str]) -> Self:
        """
        Sets multiple normal headers in the response.
        """
        for key, value in headers.items():
            self.set_header(key, value)
        return self

    def add_raw_cookie(self, cookie_header: str) -> Self:
        """
        Adds a prebuilt Set-Cookie header value.

        Example:
            response.add_raw_cookie("session=abc; Path=/; HttpOnly; Secure")
        """
        self._cookies.append(cookie_header)
        return self

    def set_cookie(
        self,
        cookie_name: str,
        value: str,
        max_age: int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        http_only: bool = True,
        same_site: str | None = "Lax",
    ) -> Self:
        """
        Adds a Set-Cookie header to the response.

        cookie_name: Cookie name
        value: Cookie value
        max_age: Max age of the cookie in seconds
        path: Path where the cookie is available
        domain: Domain where the cookie is available
        secure: Cookie is sent only over HTTPS
        http_only: Cookie is inaccessible to JavaScript
        same_site: SameSite policy, e.g. 'Lax', 'Strict', 'None'
        """
        cookie_parts = [f"{cookie_name}={value}"]

        if max_age is not None:
            cookie_parts.append(f"Max-Age={max_age}")
        if path:
            cookie_parts.append(f"Path={path}")
        if domain:
            cookie_parts.append(f"Domain={domain}")
        if secure:
            cookie_parts.append("Secure")
        if http_only:
            cookie_parts.append("HttpOnly")
        if same_site:
            cookie_parts.append(f"SameSite={same_site}")

        self._cookies.append("; ".join(cookie_parts))
        return self

    def delete_cookie(
        self,
        cookie_name: str,
        path: str = "/",
        domain: str | None = None,
        same_site: str | None = "Lax",
    ) -> Self:
        """
        Deletes a cookie by sending a Set-Cookie header with Max-Age=0 and a past Expires value.
        """
        cookie_parts = [
            f"{cookie_name}=",
            "Max-Age=0",
            "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
        ]

        if path:
            cookie_parts.append(f"Path={path}")
        if domain:
            cookie_parts.append(f"Domain={domain}")
        if same_site:
            cookie_parts.append(f"SameSite={same_site}")

        self._cookies.append("; ".join(cookie_parts))
        return self

    @property
    def cookies(self) -> tuple[str, ...]:
        """
        Returns all queued Set-Cookie header values.
        """
        return tuple(self._cookies)

    def clear_cookies(self) -> Self:
        """
        Removes all queued cookies from the response.
        """
        self._cookies.clear()
        return self

    @property
    def content_type(self) -> Optional[str]:
        """
        Gets the raw Content-Type header value, if present.
        """
        return self.headers.get("content-type")

    def set_zero_copy(self, data: Any) -> Self:
        """
        Sets zero-copy data for range or file responses.
        """
        self._zero_copy = data
        return self

    @property
    def zero_copy(self) -> Any:
        """
        Returns zero-copy data.
        """
        return self._zero_copy

    def _set_expected_body_type(self, t: Optional[Type[Any]]) -> None:
        self._expected_body_type = t

    def expected_body_type(self) -> Optional[Type[Any]]:
        return self._expected_body_type

    async def send(self, message: dict[str, Any]) -> None:
        await self._request.send(message)

    def stream(
        self,
        iterable: AsyncIterable[bytes] | Iterable[bytes],
        media_type: str = MediaType.APPLICATION_OCTET_STREAM.value,
    ) -> Self:
        """
        Creates a streaming response for bytes.
        """
        self._stream = iterable
        self.media_type = media_type
        self.charset = None
        self.body = None
        return self

    def stream_text(
        self,
        iterable: AsyncIterable[str] | Iterable[str],
        media_type: str = MediaType.TEXT_PLAIN.value,
        charset: str = "utf-8",
    ) -> Self:
        """
        Creates a streaming text response.
        """

        async def _aiter() -> AsyncIterator[bytes]:
            if hasattr(iterable, "__aiter__"):
                async for chunk in iterable:  # type: ignore[attr-defined]
                    yield str(chunk).encode(charset)
            else:
                for chunk in iterable:  # type: ignore[operator]
                    yield str(chunk).encode(charset)

        self._stream = _aiter()
        self.media_type = media_type
        self.charset = charset
        self.body = None
        return self

    @property
    def stream_iterable(self) -> Optional[AsyncIterable[bytes] | Iterable[bytes]]:
        return self._stream

    @property
    def is_streaming(self) -> bool:
        return self._stream is not None

    @property
    def app(self) -> "Patera":
        """
        Returns application reference.
        """
        return self._app

    @property
    def request(self) -> "Request":
        """
        Returns the request associated with this response.
        """
        return self._request

    @property
    def req(self) -> "Request":
        """
        Returns the request associated with this response.
        """
        return self._request

    @staticmethod
    def _parse_content_type(content_type: str) -> tuple[str, Optional[str]]:
        """
        Parses a Content-Type header into media type and optional charset.
        """
        parts = [part.strip() for part in content_type.split(";")]
        media_type = parts[0]
        charset: Optional[str] = None

        for param in parts[1:]:
            if param.lower().startswith("charset="):
                charset = param.split("=", 1)[1].strip()

        return media_type, charset
