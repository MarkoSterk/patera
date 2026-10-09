from __future__ import annotations

import pytest
from pydantic import BaseModel

from patera import HttpStatus
from patera.media_types import MediaType

from tests.helpers import make_request


@pytest.fixture
def app(make_app):
    return make_app(
        files={"templates/hello.html": "Hello {{ name }} {{ request.path }}"}
    )


@pytest.fixture
def res(app):
    return make_request(app).res


@pytest.mark.parametrize(
    "builder",
    [
        lambda r: r.text("x"),
        lambda r: r.html_body("<p>x</p>"),
        lambda r: r.xml("<x/>"),
        lambda r: r.csv("a,b"),
        lambda r: r.yaml("a: 1"),
        lambda r: r.ndjson([{"a": 1}]),
        lambda r: r.bytes(b"x"),
        lambda r: r.json({"a": 1}),
    ],
)
def test_body_builders_keep_explicit_status(res, builder):
    res.status(HttpStatus.CREATED)
    builder(res)
    assert int(res.status_code) == 201


def test_json_sets_media_type(res):
    res.json({"a": 1})
    assert res.media_type == MediaType.APPLICATION_JSON.value
    assert res.charset == "utf-8"


def test_set_header_normalizes_and_parses_content_type(res):
    res.set_header("Content-Type", "text/csv; charset=latin-1")
    assert res.headers == {"content-type": "text/csv; charset=latin-1"}
    assert res.media_type == "text/csv"
    assert res.charset == "latin-1"


def test_set_cookie_header_is_rejected(res):
    with pytest.raises(ValueError):
        res.set_header("Set-Cookie", "a=b")


def test_cookies(res):
    res.set_cookie("session", "abc", max_age=60, secure=True)
    res.delete_cookie("old")
    res.add_raw_cookie("raw=1; Path=/")
    cookies = res.cookies
    assert (
        cookies[0] == "session=abc; Max-Age=60; Path=/; Secure; HttpOnly; SameSite=Lax"
    )
    assert cookies[1].startswith("old=; Max-Age=0; Expires=Thu, 01 Jan 1970")
    assert cookies[2] == "raw=1; Path=/"
    res.clear_cookies()
    assert res.cookies == ()


def test_redirect_and_no_content(res):
    res.json({"a": 1}).redirect("/elsewhere")
    assert res.headers["location"] == "/elsewhere"
    assert int(res.status_code) == 303
    assert res.body is None
    res.no_content()
    assert int(res.status_code) == 204


def test_problem_details(res):
    res.problem("Not found", "No such user", HttpStatus.NOT_FOUND, extra={"id": 1})
    assert res.media_type == MediaType.APPLICATION_PROBLEM_JSON.value
    assert res.body == {
        "type": "about:blank",
        "title": "Not found",
        "status": 404,
        "detail": "No such user",
        "id": 1,
    }
    assert int(res.status_code) == 404


def test_reset_clears_state(res):
    res.json({"a": 1}).status(500).set_header("x-a", "1").set_cookie("a", "b")
    res.stream([b"x"])
    res.set_zero_copy({"file_path": "x", "start": 0, "length": 1})
    res._set_expected_body_type(dict)
    res.reset()
    assert int(res.status_code) == 200
    assert res.headers == {}
    assert res.body is None
    assert res.cookies == ()
    assert not res.is_streaming
    assert res.zero_copy is None
    assert res.expected_body_type() is None


async def test_html_renders_template_without_mutating_context(res):
    context = {"name": "Ana"}
    await res.status(404).html("hello.html", context)
    assert res.body == "Hello Ana /"
    assert int(res.status_code) == 404  # explicit status is kept
    assert context == {"name": "Ana"}


async def test_html_from_string(res):
    await res.html_from_string("{{ len(items) }}", {"items": [1, 2]})
    assert res.body == "2"
    assert res.media_type == MediaType.TEXT_HTML.value


async def test_stream_text_encodes_chunks(res):
    async def gen():
        yield "a"
        yield "č"

    res.stream_text(gen())
    chunks = [c async for c in res.stream_iterable]
    assert chunks == [b"a", "č".encode()]
    assert res.is_streaming


class Model(BaseModel):
    a: int
