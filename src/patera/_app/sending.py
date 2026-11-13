"""
Writes a Response to the ASGI send channel: regular, streaming and
zero-copy file responses.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import (
    Any,
    Optional,
    Type,
    AsyncIterable,
    Union,
)
import aiofiles


from ..http_methods import HttpMethod
from ..response import Response
from ..utilities import (
    encode_response_headers,
)

from ._base import AppPart


class ResponseSender(AppPart):
    """
    Writes a Response to the ASGI send channel: regular, streaming and
    zero-copy file responses.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    async def iterate_stream(
        self,
        iterable: Union[AsyncIterable[bytes], Iterable[bytes]],
    ) -> AsyncIterator[bytes]:
        """
        Normalizes async/sync iterables into an async iterator of bytes.
        Accepts bytes/bytearray/str chunks and encodes/normalizes to bytes.
        """
        app = self._app

        async def _aiter_from_sync(sync_iter: Iterable[bytes]) -> AsyncIterator[bytes]:
            for chunk in sync_iter:
                yield app._normalize_chunk(chunk)

        if hasattr(iterable, "__aiter__"):
            async for chunk in iterable:  # type: ignore[attr-defined]
                yield app._normalize_chunk(chunk)
        else:
            async for chunk in _aiter_from_sync(iterable):  # type: ignore[arg-type]
                yield chunk

    def normalize_chunk(self, chunk: Any) -> bytes:
        if isinstance(chunk, (bytes, bytearray)):
            return bytes(chunk)

        if isinstance(chunk, str):
            return chunk.encode("utf-8")

        raise TypeError(
            f"Streaming chunks must be bytes, bytearray or str, got {type(chunk)!r}"
        )

    async def send_response(
        self,
        res: Response,
        send,
        response_type: Optional[Type[Any]] = None,
    ):
        """
        Sends response.

        Serialization is delegated to the response renderer / serializer registry.
        This method focuses on transport concerns:
            - zero-copy responses
            - streaming responses
            - normal ASGI start/body sending
        """
        app = self._app
        app.response_renderer.apply_default_content_type(res)
        app._log_response(res.request, res.status_code)

        is_head = res.request.method == HttpMethod.HEAD.value

        if res.zero_copy is not None:
            params = res.zero_copy
            file_path = params["file_path"]
            start = params["start"]
            length = params["length"]

            app.response_renderer.finalize_headers(
                res,
                body_bytes=None,
                is_streaming=True,
            )
            res.headers["content-length"] = str(length)

            await send(
                {
                    "type": "http.response.start",
                    "status": int(res.status_code),
                    "headers": encode_response_headers(res),
                }
            )

            if is_head or length <= 0:
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
                return

            chunk_size = 1 * 1024 * 1024
            remaining = length

            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)

                while remaining > 0:
                    to_read = min(remaining, chunk_size)
                    chunk = await f.read(to_read)

                    if not chunk:
                        await send(
                            {
                                "type": "http.response.body",
                                "body": b"",
                                "more_body": False,
                            }
                        )
                        break

                    remaining -= len(chunk)

                    await send(
                        {
                            "type": "http.response.body",
                            "body": chunk,
                            "more_body": remaining > 0,
                        }
                    )

            return

        if res.is_streaming:
            app.response_renderer.finalize_headers(
                res,
                body_bytes=None,
                is_streaming=True,
            )

            await send(
                {
                    "type": "http.response.start",
                    "status": int(res.status_code),
                    "headers": encode_response_headers(res),
                }
            )

            stream_iter = res.stream_iterable

            if stream_iter is None or is_head:
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                        "more_body": False,
                    }
                )
                return

            async for chunk in app._iterate_stream(stream_iter):
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )

            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )
            return

        body_bytes = await app.response_renderer.render_body(res, response_type)

        app.response_renderer.finalize_headers(
            res,
            body_bytes=body_bytes,
            is_streaming=False,
        )
        await send(
            {
                "type": "http.response.start",
                "status": int(res.status_code),
                "headers": encode_response_headers(res),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"" if is_head else (body_bytes or b""),
                "more_body": False,
            }
        )
