"""
Response class. Holds all information regarding responses to individual requests
"""

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
    from .pyjolt import PyJolt
    from .request import Request

U = TypeVar("U")


class Response(Generic[U]):
    """
    Response class of application. Holds all data (headers, body, status_code of the response)
    Example return of route handler:
    ```
    return res.json({"message": "My message", "status": "some status"}).status(200)
    ```
    """

    def __init__(self, app: "PyJolt", request: "Request") -> None:
        self._app = app
        self._request = request
        self.status_code: int | HttpStatus = HttpStatus.OK  # default status code is 200
        self.headers: dict = {}
        self.body: Optional[U] = None
        self.render_engine = self._app.jinja_environment
        self._zero_copy = None
        self._expected_body_type: Optional[Type[Any]] = None

        self._stream: Optional[AsyncIterable[bytes] | Iterable[bytes]] = None

    def status(self, status_code: int | HttpStatus) -> Self:
        """
        Sets status code of response
        """
        self.status_code = status_code
        return self

    def redirect(
        self, location: str, status_code: int | HttpStatus = HttpStatus.SEE_OTHER
    ) -> Self:
        """
        Redirects the client to the provided location
        """
        self.set_header("location", location)
        self.status_code = status_code
        self.body = None
        return self

    def json(self, data: Any) -> Self:
        """
        Sets data to response body and creates appropriate
        response headers. Sets default response status to 200
        """
        self.headers["content-type"] = MediaType.APPLICATION_JSON.value
        self.body = data
        return self

    def no_content(self) -> Self:
        """
        Returns a response with no content (body) and status 204
        """
        self.body = None
        self.status(204)
        return self

    def text(self, text: str) -> Self:
        """
        Creates text response with text/html content-type
        """
        self.body = cast(U, text.encode("utf-8"))
        self.status(HttpStatus.OK)
        return self

    async def html_from_string(
        self, text: str, context: Optional[dict[str, Any]] = None
    ) -> Self:
        """
        Creates text response with text/html content-type
        """
        if context is None:
            context = {}
        for method in self.app.global_context_methods:
            additional_context = await run_sync_or_async(method)
            if not isinstance(additional_context, dict):
                raise ValueError(
                    "Return of global context method must be off type dictionary"
                )
            context.update(additional_context)
        self.headers["content-type"] = "text/html"
        context["app"] = self.app
        context["url_for"] = self.app.url_for
        context["request"] = self._request
        context["attribute"] = getattr
        context["len"] = len
        rendered = await self.render_engine.from_string(text).render_async(
            **context
        )  # self.render_engine.from_string(text).render(**context)
        # self.body = text.encode("utf-8")
        self.body = cast(U, rendered.encode("utf-8"))
        self.status(HttpStatus.OK)
        return self

    async def html(
        self, template_path: str, context: Optional[dict[str, Any]] = None
    ) -> Self:
        """
        Renders html template and creates response with text/html content-type
        and default status code 200

        template_path: relative path of template inside the templates folder
        context: dictionary with data used in the template
        """

        if context is None:
            context = {}

        for method in self.app.global_context_methods:
            additional_context = await run_sync_or_async(method)
            if not isinstance(additional_context, dict):
                raise ValueError(
                    "Return of global context method must be off type dictionary"
                )
            context = {**context, **additional_context}
        context["app"] = self.app
        context["url_for"] = self.app.url_for
        context["request"] = self._request
        context["attribute"] = getattr
        context["len"] = len

        template = self.render_engine.get_template(template_path)
        rendered = await template.render_async(**context)
        self.headers["content-type"] = "text/html"
        self.body = cast(U, rendered.encode("utf-8"))
        self.status(HttpStatus.OK)
        return self

    def send_file(self, body, headers) -> Self:
        """
        For sending files
        Sets correct headers and body of the response
        """
        for k, v in headers.items():
            self.headers[k] = v
        self.body = body
        return self

    def set_header(self, key: str, value: str) -> Self:
        """
        Sets or updates a header in the response.

        key: Header name
        value: Header value
        """
        self.headers[key.lower()] = value
        return self

    def set_headers(self, headers: dict[str, str]) -> Self:
        """
        Sets multiple headers in the response.

        headers: Dictionary of headers to set
        """
        for key, value in headers.items():
            self.set_header(key, value)
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
    ) -> Self:
        """
        Sets a cookie in the response.

        cookie_name: Cookie name
        value: Cookie value
        max_age: Max age of the cookie in seconds (optional)
        path: Path where the cookie is available (default "/")
        domain: Domain where the cookie is available (optional)
        secure: If True, the cookie is only sent over HTTPS (default False)
        http_only: If True, the cookie is inaccessible to JavaScript (default True) <-- MORE SECURE
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

        cookie_header = "; ".join(cookie_parts)
        if "set-cookie" in self.headers:
            self.headers["set-cookie"] += f", {cookie_header}"
        else:
            self.headers["set-cookie"] = cookie_header

        return self

    @property
    def content_type(self) -> str:
        """
        Gets the Content-Type header of the response.
        content_type: The MIME type to set as the Content-Type
        """
        return cast(str, self.headers.get("content-type", None))

    def delete_cookie(
        self, cookie_name: str, path: str = "/", domain: Optional[str] = None
    ) -> Self:
        """
        Deletes a cookie by setting its Max-Age to 0.

        cookie_name: Cookie name
        path: Path where the cookie was available (default "/")
        domain: Domain where the cookie was available (optional)
        """
        cookie_parts = [f"{cookie_name}=", "Max-Age=0", f"Path={path}"]

        if domain:
            cookie_parts.append(f"Domain={domain}")

        cookie_header = "; ".join(cookie_parts)
        if "set-cookie" in self.headers:
            self.headers["set-cookie"] += f", {cookie_header}"
        else:
            self.headers["set-cookie"] = cookie_header

        return self

    def set_zero_copy(self, data) -> Self:
        """Sets zero copy data for range responses"""
        self._zero_copy = data
        return self

    def _set_expected_body_type(self, t: Optional[Type[Any]]) -> None:
        self._expected_body_type = t

    def expected_body_type(self) -> Optional[Type[Any]]:
        return self._expected_body_type

    async def send(self, message: dict) -> None:
        return await self._request.send(message)

    def stream(self, iterable: AsyncIterable[bytes] | Iterable[bytes]) -> Self:
        """
        Method for streaming response

        iterable: async or sync iterable yielding bytes (or bytearray/str)
        content_type: MIME type of the stream
        """
        self._stream = iterable
        self.headers["content-type"] = MediaType.APPLICATION_OCTET_STREAM.value
        # Body must be None so the app knows to stream
        self.body = None
        return self

    def stream_text(self, iterable: AsyncIterable[str] | Iterable[str]) -> Self:
        """
        Method for streaming text response
        """

        async def _aiter() -> AsyncIterator[bytes]:
            if hasattr(iterable, "__aiter__"):
                async for chunk in iterable:  # type: ignore[attr-defined]
                    yield str(chunk).encode("utf-8")
            else:
                for chunk in iterable:  # type: ignore[operator]
                    yield str(chunk).encode("utf-8")

        self._stream = _aiter()
        self.headers["content-type"] = MediaType.TEXT_PLAIN.value + "; charset=utf-8"
        self.body = None
        return self

    @property
    def stream_iterable(self) -> Optional[AsyncIterable[bytes] | Iterable[bytes]]:
        return self._stream

    @property
    def is_streaming(self) -> bool:
        return self._stream is not None

    @property
    def zero_copy(self):
        """Returns zero copy data"""
        return self._zero_copy

    @property
    def app(self):
        """
        Returns application reference
        """
        return self._app
