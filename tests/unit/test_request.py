from __future__ import annotations

import pytest

from patera.exceptions import (
    ClientDisconnected,
    InvalidRequestBody,
    RequestBodyTooLarge,
)
from patera.request import UploadedFile

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


async def test_empty_json_is_none(app):
    assert await make_request(app, "POST").json() is None


async def test_malformed_json_raises_bad_request(app):
    with pytest.raises(InvalidRequestBody) as exc:
        await make_request(app, "POST", body=b"{not json").json()
    assert exc.value.status_code == 400
    assert exc.value.message == "Malformed JSON body"
    with pytest.raises(InvalidRequestBody):
        await make_request(app, "POST", body=b"\xff\xfe").json()


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
        # lower-case header names on purpose (the parser ignores case)
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


async def test_uploaded_bytes_are_kept_exactly(app):
    # Content that looks like a part boundary followed by headers must not be
    # rewritten: a Markdown file with front matter (CRLF lines) looks like this.
    content = b"line one\r\n---\r\ntitle:Hello\r\nx-y-z:  spaced\r\n\r\nbody\r\n--\r\n"
    boundary = "XyZ123"
    body = _multipart(boundary, [("doc", "notes.md", content, "text/markdown")])
    req = make_request(
        app,
        "POST",
        body=body,
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    files = await req.files()
    assert files["doc"].read() == content


async def test_multipart_names_are_utf8(app):
    boundary = "XyZ123"
    body = _multipart(boundary, [("dokument", "poročilo.pdf", b"%PDF", None)])
    req = make_request(
        app,
        "POST",
        body=body,
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    upload = (await req.files())["dokument"]
    assert upload.filename == "poročilo.pdf"
    assert upload.content_type == "application/octet-stream"


@pytest.mark.parametrize(
    "content_type, body",
    [
        ("multipart/form-data; boundary=xyz", b"garbage"),
        ("multipart/form-data", b"garbage"),
    ],
)
async def test_malformed_multipart_is_a_bad_request(app, content_type, body):
    req = make_request(app, "POST", body=body, headers={"content-type": content_type})
    with pytest.raises(InvalidRequestBody):
        await req.form()


async def test_disconnect_before_the_body_is_complete(app):
    req = make_request(app, "POST", body=b"abc", disconnect=True)
    with pytest.raises(ClientDisconnected):
        await req.body()


def test_uploaded_file_reads_like_a_file(tmp_path):
    import shutil

    upload = UploadedFile("a.bin", b"0123456789", "application/octet-stream")
    assert upload.read(4) == b"0123"
    assert upload.read(4) == b"4567"
    assert upload.read() == b"89"
    assert upload.read(4) == b""
    upload.seek(0)
    target = tmp_path / "copy.bin"
    with target.open("wb") as out:
        shutil.copyfileobj(upload, out, 3)
    assert target.read_bytes() == b"0123456789"


def test_raw_bytes_in_the_query_string(app):
    req = make_request(app, query_string=b"a=\xff")
    assert req.query_string == "a=\ufffd"


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


def _chunked_request(app, *chunks: bytes, headers=None):
    from patera.request import Request
    from tests.helpers import make_receive, make_scope

    async def send(message):
        pass

    return Request(
        make_scope("POST", "/", headers=headers),
        make_receive(*chunks),
        send,
        app,
        {},
        lambda: None,
    )


async def test_body_limit_applies_while_reading(make_app):
    app = make_app(MAX_CONTENT_LENGTH=10)
    # No Content-Length: the limit is enforced as chunks arrive.
    req = _chunked_request(app, b"12345", b"67890", b"x")
    with pytest.raises(RequestBodyTooLarge) as exc:
        await req.body()
    assert exc.value.status_code == 413
    assert exc.value.data == {"max_content_length": 10}
    assert await _chunked_request(app, b"12345", b"67890").body() == b"1234567890"


async def test_declared_content_length_is_refused_before_reading(make_app):
    from patera.request import Request
    from tests.helpers import make_scope

    app = make_app(MAX_CONTENT_LENGTH=10)

    async def receive():
        raise AssertionError("the body must not be read")

    async def send(message):
        pass

    req = Request(
        make_scope("POST", "/", headers={"content-length": "11"}),
        receive,
        send,
        app,
        {},
        lambda: None,
    )
    with pytest.raises(RequestBodyTooLarge):
        await req.body()


async def test_max_content_length_can_be_changed_per_request(make_app):
    app = make_app(MAX_CONTENT_LENGTH=4)
    req = _chunked_request(app, b"123456")
    assert req.max_content_length == 4
    req.max_content_length = None
    assert await req.body() == b"123456"
    with pytest.raises(ValueError):
        req.max_content_length = -1


def test_max_content_length_decorator_rejects_negative_values():
    from patera.controller import max_content_length

    with pytest.raises(ValueError):
        max_content_length(-1)


def test_repeated_headers_are_combined_and_listed(app):
    req = make_request(app, headers={"accept": "text/html"})
    req.scope["headers"] += [
        (b"accept", b"application/json"),
        (b"cookie", b"a=1"),
        (b"cookie", b"b=2"),
    ]
    assert req.headers["accept"] == "text/html, application/json"
    assert req.headers["cookie"] == "a=1; b=2"
    assert req.header_list("Accept") == ["text/html", "application/json"]
    assert req.header_list("x-missing") == []


def test_cookies_are_parsed_and_malformed_pairs_skipped(app):
    req = make_request(app, headers={"cookie": 'session=abc; theme="dark"; ;bad pair'})
    req.scope["headers"].append((b"cookie", b"lang=sl"))
    assert req.cookies == {"session": "abc", "theme": "dark", "lang": "sl"}
    assert make_request(app).cookies == {}


def test_blank_query_values_are_kept(app):
    req = make_request(app, query_string=b"q=&tag=a&tag=&flag")
    assert req.query_parameters["q"] == ""
    assert req.query_parameters["tag"] == ["a", ""]
    assert req.query_list("tag") == ["a", ""]
    assert req.query_list("q") == [""]
    assert req.query_list("missing") == []


async def test_blank_form_values_are_kept(app):
    req = make_request(
        app,
        "POST",
        body=b"name=&tag=a&tag=b",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    form = await req.form()
    assert form["name"] == ""
    assert await req.form_list("tag") == ["a", "b"]
    assert await req.form_list("name") == [""]
    assert await req.form_list("missing") == []


async def test_form_with_invalid_utf8_is_a_bad_request(app):
    req = make_request(
        app,
        "POST",
        body=b"name=\xff\xfe",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    with pytest.raises(InvalidRequestBody) as exc:
        await req.form()
    assert exc.value.status_code == 400


def test_validate_turns_invalid_client_data_into_a_422(app):
    from pydantic import BaseModel

    from patera.exceptions import RequestValidationError

    class Query(BaseModel):
        page: int

    req = make_request(app, query_string=b"page=2")
    assert req.validate(Query, req.query_parameters).page == 2
    with pytest.raises(RequestValidationError) as exc:
        req.validate(Query, {"page": "two"})
    assert exc.value.status_code == 422
    assert exc.value.errors[0]["loc"] == ("page",)
    assert "input" not in exc.value.errors[0]
