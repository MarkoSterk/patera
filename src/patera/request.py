# request.py
# pylint: disable=C0116

from __future__ import annotations

import re
import json
import base64
from io import BytesIO
from urllib.parse import parse_qs
from typing import Callable, Any, TYPE_CHECKING, Mapping, Optional, cast

import python_multipart as pm
from pydantic_core import core_schema

from .response import Response
from .ctx import current_request, CurrentContextProxy

if TYPE_CHECKING:
    from .patera import Patera


def extract_boundary(content_type: str) -> str:
    match = re.search(r'boundary="?([^";]+)"?', content_type)

    if not match:
        raise ValueError("No boundary found in Content-Type")

    return match.group(1)


def add_multi_value(target: dict[str, Any], key: str, value: Any) -> None:
    """
    Adds a value to a dictionary while preserving repeated keys.

    First value:
        target["attachment"] = file1

    Second value with same key:
        target["attachment"] = [file1, file2]

    Third value with same key:
        target["attachment"] = [file1, file2, file3]
    """
    if key not in target:
        target[key] = value
        return

    if not isinstance(target[key], list):
        target[key] = [target[key]]

    target[key].append(value)


class UploadedFile:
    """
    Wrapper around an in-memory/temporary file.
    """

    def __init__(self, filename: str, content: bytes, content_type: str):
        self.filename = filename
        self.content_type = content_type or "application/octet-stream"
        self._content = content
        self._stream = BytesIO(content)

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._content

        return self._content[:size]

    def seek(self, pos: int, whence: int = 0) -> int:
        return self._stream.seek(pos, whence)

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            self.seek(0)
            f.write(self._stream.read())

    @property
    def size(self) -> int:
        cur = self._stream.tell()
        self._stream.seek(0, 2)
        sz = self._stream.tell()
        self._stream.seek(cur)

        return sz

    @property
    def stream(self) -> BytesIO:
        return self._stream

    def get_stream(self) -> BytesIO:
        return BytesIO(self._content)

    def __repr__(self) -> str:
        return (
            f"<UploadedFile filename={self.filename!r} "
            f"size={self.size} content_type={self.content_type!r}>"
        )

    @staticmethod
    def _from_mapping(data: Mapping[str, Any]) -> "UploadedFile":
        if "filename" not in data:
            raise ValueError("UploadedFile requires 'filename'")

        filename = data["filename"]
        content_type = data.get("content_type", "application/octet-stream")

        if "content" not in data:
            raise ValueError("UploadedFile requires 'content' (bytes)")

        content = data["content"]

        if isinstance(content, (bytes, bytearray)):
            content_bytes = bytes(content)
        elif isinstance(content, memoryview):
            content_bytes = content.tobytes()
        elif isinstance(content, str):
            try:
                content_bytes = base64.b64decode(content, validate=True)
            except Exception as e:
                raise ValueError("Invalid base64 for UploadedFile.content") from e
        else:
            raise TypeError(
                "UploadedFile.content must be bytes/bytearray/memoryview or base64 str"
            )

        if not isinstance(filename, str):
            raise TypeError("UploadedFile.filename must be a string")

        if not isinstance(content_type, str):
            raise TypeError("UploadedFile.content_type must be a string")

        return UploadedFile(
            filename=filename,
            content=content_bytes,
            content_type=content_type,
        )

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: Any,
    ) -> core_schema.CoreSchema:
        def validate(v: Any) -> "UploadedFile":
            if isinstance(v, UploadedFile):
                return v

            if isinstance(v, Mapping):
                return cls._from_mapping(v)

            if isinstance(v, tuple):
                if len(v) == 2:
                    filename, content = v
                    return cls._from_mapping(
                        {
                            "filename": filename,
                            "content": content,
                        }
                    )

                if len(v) == 3:
                    filename, content, content_type = v
                    return cls._from_mapping(
                        {
                            "filename": filename,
                            "content": content,
                            "content_type": content_type,
                        }
                    )

                raise ValueError(
                    "UploadedFile tuple input must be "
                    "(filename, content) or "
                    "(filename, content, content_type)"
                )

            raise TypeError("Value is not a valid UploadedFile input")

        def serialize(v: "UploadedFile") -> dict[str, Any]:
            return {
                "filename": v.filename,
                "content_type": v.content_type,
                "size": v.size,
            }

        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize,
                info_arg=False,
                return_schema=core_schema.dict_schema(),
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: core_schema.CoreSchema,
        handler: Any,
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "title": "UploadedFile",
            "properties": {
                "filename": {"type": "string"},
                "content_type": {"type": "string"},
                "size": {"type": "integer"},
            },
            "required": ["filename"],
            "additionalProperties": True,
            "description": "In-memory uploaded file serialized as metadata by default.",
        }


def _normalize_multipart_part_headers(raw: bytes) -> bytes:
    """
    Normalize multipart part header names to canonical casing within each part
    header block.
    """
    out = bytearray()
    i = 0
    n = len(raw)

    while i < n:
        hdr_end = raw.find(b"\r\n\r\n", i)

        if hdr_end == -1:
            out.extend(raw[i:])
            break

        header_block = raw[i:hdr_end]
        rest_start = hdr_end + 4

        if b"\r\n" in header_block and b":" in header_block:
            lines = header_block.split(b"\r\n")
            new_lines = [lines[0]]

            for line in lines[1:]:
                colon = line.find(b":")

                if colon == -1:
                    new_lines.append(line)
                    continue

                name = line[:colon].strip()
                value = line[colon + 1 :].lstrip()

                lname = name.lower()

                if lname == b"content-disposition":
                    cname = b"Content-Disposition"
                elif lname == b"content-type":
                    cname = b"Content-Type"
                elif lname == b"content-length":
                    cname = b"Content-Length"
                elif lname == b"content-transfer-encoding":
                    cname = b"Content-Transfer-Encoding"
                else:
                    cname = b"-".join(
                        part[:1].upper() + part[1:].lower()
                        for part in lname.split(b"-")
                    )

                new_lines.append(cname + b": " + value)

            out.extend(b"\r\n".join(new_lines))
            out.extend(b"\r\n\r\n")
        else:
            out.extend(raw[i:rest_start])

        i = rest_start
        next_boundary = raw.find(b"\r\n--", i)

        if next_boundary == -1:
            out.extend(raw[i:])
            break

        out.extend(raw[i : next_boundary + 2])
        i = next_boundary + 2

    return bytes(out)


class Request:
    """
    ASGI-style request adapter that lazy-parses JSON, form, and multipart.
    """

    def __init__(
        self,
        scope: dict,
        receive: Callable[..., Any],
        send: Callable[..., Any],
        app: "Patera",
        route_parameters: dict | Mapping,
        route_handler: Callable,
    ):
        self._app = app
        self.scope = scope
        self._receive = receive
        self._send: Callable = send

        self._body: bytes | None = None
        self._json: dict[str, Any] | None = None
        self._form: dict[str, Any] | None = None
        self._files: dict[str, Any] | None = None

        self._user: Any = None
        self._route_parameters = route_parameters
        self._route_handler = route_handler
        self._response: Response[Any] = app.response_class(app, self)
        self._context: dict[str, Any] = {}

    @property
    def route_handler(self) -> Callable:
        return self._route_handler

    @property
    def route_parameters(self) -> dict | Mapping:
        return self._route_parameters

    @route_parameters.setter
    def route_parameters(self, rp: dict | Mapping) -> None:
        self._route_parameters = rp

    @property
    def method(self) -> str:
        return self.scope.get("method", "").upper()

    @property
    def path(self) -> str:
        return self.scope.get("path", "/")

    @property
    def query_string(self) -> str:
        return self.scope.get("query_string", b"").decode("utf-8")

    @property
    def headers(self) -> dict[str, str]:
        raw = self.scope.get("headers", [])

        return {key.decode("latin1").lower(): val.decode("latin1") for key, val in raw}

    @property
    def query_parameters(self) -> dict[str, Any]:
        qs = self.scope.get("query_string", b"")
        parsed = parse_qs(qs.decode("utf-8"))

        return {
            key: values if len(values) > 1 else values[0]
            for key, values in parsed.items()
        }

    @property
    def user(self) -> Any:
        return current_request.user

    @property
    def roles(self) -> Optional[list[Any]]:
        return current_request.roles

    @property
    def app(self) -> "Patera":
        return self._app

    def set_user(self, user: Any) -> None:
        current_request.user = user

    def set_roles(self, roles: list[Any]) -> None:
        current_request.roles = roles

    def remove_user(self) -> None:
        current_request.user = None

    async def body(self) -> bytes:
        if self._body is not None:
            return self._body

        parts: list[bytes] = []

        while True:
            msg = await self._receive()

            if msg["type"] == "http.request":
                parts.append(msg.get("body", b""))

                if not msg.get("more_body", False):
                    break

        self._body = b"".join(parts)

        return self._body

    async def json(self) -> dict[str, Any] | None:
        if self._json is not None:
            return self._json

        raw = await self.body()

        if not raw:
            return None

        try:
            self._json = json.loads(raw)
        except json.JSONDecodeError:
            self._json = None

        return self._json

    async def form(self) -> dict[str, Any]:
        if self._form is not None:
            return self._form

        ct = self.headers.get("content-type", "")

        if "multipart/form-data" in ct:
            self._form, self._files = await self._parse_multipart(ct)
        elif "application/x-www-form-urlencoded" in ct:
            raw = await self.body()
            parsed = parse_qs(raw.decode("utf-8"))

            self._form = {
                key: values if len(values) > 1 else values[0]
                for key, values in parsed.items()
            }
            self._files = {}
        else:
            self._form = {}
            self._files = {}

        return self._form

    async def files(self) -> dict[str, UploadedFile | list[UploadedFile]]:
        if self._files is None:
            await self.form()

        return self._files or {}

    async def form_and_files(self) -> dict[str, Any]:
        form_data = await self.form()
        files = await self.files()

        result = dict(form_data)

        for key, value in files.items():
            if key in result:
                add_multi_value(result, key, value)
            else:
                result[key] = value

        return result

    async def send(self, message: dict) -> None:
        return await self._send(message)

    async def receive(self) -> dict:
        return await self._receive()

    async def accept(self) -> None:
        await self._send({"type": "websocket.accept"})

    @staticmethod
    def _multipart_headers(content_type: str) -> dict[str, str]:
        return {
            "Content-Type": content_type,
            "content-type": content_type,
        }

    @staticmethod
    def _get_header_case_insensitive(hdrs: Any, key: str) -> str | None:
        if not isinstance(hdrs, dict):
            return None

        candidates: list[Any] = [
            key,
            key.lower(),
            key.upper(),
            key.encode("latin1"),
            key.lower().encode("latin1"),
            key.upper().encode("latin1"),
        ]

        for candidate_key in candidates:
            value = hdrs.get(candidate_key)

            if value is None:
                continue

            if isinstance(value, bytes):
                return value.decode("latin1")

            if isinstance(value, str):
                return value

        return None

    async def _parse_multipart(
        self, content_type: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        raw = await self.body()
        raw = _normalize_multipart_part_headers(raw)

        stream = BytesIO(raw)

        form_data: dict[str, Any] = {}
        files: dict[str, Any] = {}

        def on_field(field: Any) -> None:
            name = getattr(field, "field_name", None)

            if name is None:
                return

            value = getattr(field, "value", None)

            if isinstance(name, bytes):
                name = name.decode("latin1")

            if isinstance(value, bytes):
                value = value.decode("utf-8", "replace")

            add_multi_value(form_data, name, cast(str, value))

        def on_file(f: Any) -> None:
            raw_name = getattr(f, "field_name", None)

            if raw_name is None:
                return

            raw_filename = getattr(f, "file_name", b"") or b""

            name = (
                raw_name.decode("latin1") if isinstance(raw_name, bytes) else raw_name
            )

            filename = (
                raw_filename.decode("latin1")
                if isinstance(raw_filename, bytes)
                else raw_filename
            )

            fileobj = f.file_object
            fileobj.seek(0)
            content = fileobj.read()

            headers = getattr(f, "headers", {}) or {}
            part_content_type = (
                self._get_header_case_insensitive(headers, "Content-Type")
                or "application/octet-stream"
            )

            uploaded_file = UploadedFile(
                filename=filename,
                content=content,
                content_type=part_content_type,
            )

            add_multi_value(files, name, uploaded_file)

        pm.parse_form(
            headers={
                "Content-Type": content_type,
                "content-type": content_type,
            },
            input_stream=stream,
            on_field=on_field,
            on_file=on_file,
        )

        return form_data, files

    async def get_data(self, location: str = "json") -> dict[str, Any] | None:
        if location == "json":
            return await self.json()

        if location == "form":
            return await self.form()

        if location == "files":
            return await self.files()

        if location == "form_and_files":
            return await self.form_and_files()

        if location == "query":
            return self.query_parameters

        return None

    @property
    def response(self) -> Response:
        return self._response

    @property
    def res(self) -> Response:
        return self._response

    @property
    def context(self) -> CurrentContextProxy:
        return current_request
