from __future__ import annotations

import pytest

from patera.request import UploadedFile, extract_boundary

from tests.helpers import make_request


@pytest.fixture
def app(make_app):
    return make_app()


def test_basic_properties(app):
    req = make_request(
        app,
        "post",
        "/x",
        headers={"X-Token": "abc"},
        query_string=b"a=1&b=2&b=3&c=%C4%8D",
        route_parameters={"id": 1},
    )
    assert req.method == "POST"
    assert req.path == "/x"
    assert req.headers["x-token"] == "abc"
    assert req.query_parameters == {"a": "1", "b": ["2", "3"], "c": "č"}
    assert req.route_parameters == {"id": 1}
    req.add_route_parameter("slug", "s")
    req.add_route_parameters({"page": 2})
    assert req.route_parameters == {"id": 1, "slug": "s", "page": 2}
    assert req.res is req.response


async def test_json_body_and_caching(app):
    req = make_request(app, "POST", body=b'{"a": 1}')
    assert await req.json() == {"a": 1}
    assert await req.json() == {"a": 1}  # cached; receive is not called again
    assert await req.body() == b'{"a": 1}'


async def test_invalid_or_empty_json_is_none(app):
    assert await make_request(app, "POST", body=b"{not json").json() is None
    assert await make_request(app, "POST").json() is None


async def test_body_stops_on_client_disconnect(app):
    req = make_request(app, "POST", body=b"partial", disconnect=True)
    assert await req.body() == b"partial"


async def test_urlencoded_form(app):
    req = make_request(
        app,
        "POST",
        body=b"name=Ana&tag=a&tag=b",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert await req.form() == {"name": "Ana", "tag": ["a", "b"]}
    assert await req.files() == {}
    assert await req.get_data("form") == {"name": "Ana", "tag": ["a", "b"]}
    assert await req.get_data("unknown") is None


def _multipart(boundary: str, parts: list[tuple[str, str | None, bytes, str | None]]):
    out = b""
    for name, filename, content, ctype in parts:
        out += f"--{boundary}\r\n".encode()
        disposition = f'form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        # lower-case header names on purpose (normalized by the parser)
        out += f"content-disposition: {disposition}\r\n".encode()
        if ctype:
            out += f"content-type: {ctype}\r\n".encode()
        out += b"\r\n" + content + b"\r\n"
    return out + f"--{boundary}--\r\n".encode()


async def test_multipart_form_and_files(app):
    boundary = "XyZ123"
    body = _multipart(
        boundary,
        [
            ("title", None, "Šola".encode(), None),
            ("doc", "a.txt", b"first", "text/plain"),
            ("doc", "b.bin", b"\x00\x01", "application/octet-stream"),
        ],
    )
    req = make_request(
        app,
        "POST",
        body=body,
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    form = await req.form()
    files = await req.files()
    assert form == {"title": "Šola"}
    docs = files["doc"]
    assert isinstance(docs, list) and len(docs) == 2
    assert docs[0].filename == "a.txt"
    assert docs[0].read() == b"first"
    assert docs[0].content_type == "text/plain"
    assert docs[1].size == 2
    combined = await req.form_and_files()
    assert combined["title"] == "Šola"
    assert len(combined["doc"]) == 2


def test_extract_boundary():
    assert extract_boundary('multipart/form-data; boundary="abc"') == "abc"
    with pytest.raises(ValueError):
        extract_boundary("multipart/form-data")


def test_uploaded_file_pydantic_roundtrip(tmp_path):
    from pydantic import BaseModel

    class Upload(BaseModel):
        file: UploadedFile

    model = Upload.model_validate(
        {"file": {"filename": "a.txt", "content": "aGk=", "content_type": "text/plain"}}
    )
    assert model.file.read() == b"hi"
    target = tmp_path / "out.txt"
    model.file.save(str(target))
    assert target.read_bytes() == b"hi"
    dumped = model.model_dump()
    assert dumped["file"]["filename"] == "a.txt"
