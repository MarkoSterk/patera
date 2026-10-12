"""
Request size limits, streamed NDJSON responses and overriding a default
serializer, exercised through the test client.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from pydantic import BaseModel

from patera import MediaType, Request, Response
from patera.controller import (
    Controller,
    before_request,
    consumes,
    get,
    max_content_length,
    path,
    post,
)
from patera.serializers import JsonSerializer

pytestmark = pytest.mark.integration


class Note(BaseModel):
    text: str


class Row(BaseModel):
    id: int


@path("/limits")
class LimitsController(Controller):
    @post("/json")
    @consumes(MediaType.APPLICATION_JSON)
    async def json_note(self, req: Request, note: Note) -> Response:
        return req.res.json({"length": len(note.text)})

    @post("/form")
    async def form(self, req: Request) -> Response:
        return req.res.json({"fields": len(await req.form())})

    @post("/upload")
    @max_content_length(64 * 1024)
    async def upload(self, req: Request) -> Response:
        files = await req.files()
        return req.res.json({"files": len(files)})

    @post("/unlimited")
    @max_content_length(None)
    async def unlimited(self, req: Request) -> Response:
        return req.res.json({"size": len(await req.body())})

    @get("/untouched")
    async def untouched(self, req: Request) -> Response:
        return req.res.text("no body read")


@path("/hooked")
class HookedController(Controller):
    @before_request
    async def raise_limit(self, req: Request) -> None:
        req.max_content_length = 4096

    @post("/")
    async def index(self, req: Request) -> Response:
        return req.res.json({"size": len(await req.body())})


@pytest.fixture
def app(make_app):
    return make_app(
        controllers=[LimitsController, HookedController],
        MAX_CONTENT_LENGTH=1024,
        DEBUG=False,
    )


def _assert_too_large(res, limit: int) -> None:
    assert res.status_code == 413
    body = res.json()
    assert body["status"] == "error"
    assert body["message"] == "Request body too large"
    assert body["data"] == {"max_content_length": limit}


async def test_body_within_the_limit(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/limits/json", json={"text": "x" * 500})
    assert res.status_code == 200
    assert res.json() == {"length": 500}


@pytest.mark.parametrize("route", ["/limits/json", "/limits/form"])
async def test_body_over_the_limit_is_413(app, client_for, route):
    async with client_for(app) as client:
        if route.endswith("json"):
            res = await client.post(route, json={"text": "x" * 2000})
        else:
            res = await client.post(route, data={"text": "x" * 2000})
    _assert_too_large(res, 1024)


async def test_endpoint_decorator_raises_the_limit(app, client_for):
    payload = {"file": ("data.bin", b"\x00" * 10_000, "application/octet-stream")}
    async with client_for(app) as client:
        res = await client.post("/limits/upload", files=payload)
        assert res.status_code == 200
        assert res.json() == {"files": 1}
        big = {"file": ("data.bin", b"\x00" * 100_000, "application/octet-stream")}
        res = await client.post("/limits/upload", files=big)
    _assert_too_large(res, 64 * 1024)


async def test_endpoint_decorator_can_remove_the_limit(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/limits/unlimited", content=b"x" * 50_000)
    assert res.json() == {"size": 50_000}


async def test_before_request_hook_can_change_the_limit(app, client_for):
    async with client_for(app) as client:
        assert (await client.post("/hooked/", content=b"x" * 3000)).json() == {
            "size": 3000
        }
        _assert_too_large(await client.post("/hooked/", content=b"x" * 5000), 4096)


async def test_limit_disabled_by_setting(make_app, client_for):
    app = make_app(controllers=[LimitsController], MAX_CONTENT_LENGTH=None)
    async with client_for(app) as client:
        res = await client.post("/limits/json", json={"text": "x" * 20_000})
    assert res.json() == {"length": 20_000}


async def test_default_limit_is_ten_megabytes(make_app):
    app = make_app()
    assert app.configs.MAX_CONTENT_LENGTH == 10 * 1024 * 1024


async def test_endpoints_that_do_not_read_the_body_are_unaffected(app, client_for):
    async with client_for(app) as client:
        res = await client.request("GET", "/limits/untouched", content=b"x" * 5000)
    assert res.text == "no body read"


# ---- Streamed NDJSON -----------------------------------------------------------

produced: list[int] = []


@path("/export")
class ExportController(Controller):
    @get("/list")
    async def as_list(self, req: Request) -> Response[list[Row]]:
        return req.res.ndjson([{"id": 1, "extra": "x"}, {"id": 2}])

    @get("/generator")
    async def generator(self, req: Request) -> Response[Row]:
        def rows() -> Iterator[dict]:
            for i in range(3):
                produced.append(i)
                yield {"id": i, "dropped": True}

        return req.res.ndjson(rows())

    @get("/async")
    async def async_rows(self, req: Request) -> Response:
        async def rows() -> AsyncIterator[Row]:
            for i in range(3):
                await asyncio.sleep(0)
                yield Row(id=i)

        return req.res.ndjson(rows())


async def test_ndjson_list_is_sent_in_one_piece(make_app, client_for):
    app = make_app(controllers=[ExportController])
    async with client_for(app) as client:
        res = await client.get("/export/list")
    assert res.headers["content-type"].startswith("application/x-ndjson")
    assert res.headers["content-length"] == str(len(res.content))
    assert res.text == '{"id":1}\n{"id":2}\n'


@pytest.mark.parametrize("route", ["/export/generator", "/export/async"])
async def test_ndjson_iterators_are_streamed(make_app, client_for, route):
    app = make_app(controllers=[ExportController])
    produced.clear()
    async with client_for(app) as client:
        res = await client.get(route)
    assert res.headers["content-type"].startswith("application/x-ndjson")
    assert "content-length" not in res.headers
    # Rows are validated through Response[Row]; extra keys are dropped.
    assert res.text == '{"id":0}\n{"id":1}\n{"id":2}\n'


async def test_ndjson_stream_is_lazy(make_app):
    app = make_app(controllers=[ExportController])
    from tests.helpers import make_request

    produced.clear()
    req = make_request(app)

    def rows():
        for i in range(2):
            produced.append(i)
            yield {"id": i}

    res = req.res.ndjson(rows())
    assert res.is_streaming
    assert produced == []  # nothing is produced until the response is sent
    chunks = [chunk async for chunk in res.stream_iterable]
    assert chunks == [b'{"id":0}\n', b'{"id":1}\n']
    assert produced == [0, 1]


# ---- Overriding a default serializer ------------------------------------------


class ShoutingJson(JsonSerializer):
    async def serialize(self, response, response_type=None):
        data = await JsonSerializer.serialize(self, response, response_type)
        return (data or b"").upper()


@path("/shout")
class ShoutController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.json({"word": "hello"})


async def test_registering_first_overrides_a_default(make_app, client_for):
    app = make_app(controllers=[ShoutController])
    app.response_serializers.register(ShoutingJson(), first=True)
    async with client_for(app) as client:
        res = await client.get("/shout/")
    assert res.text == '{"WORD":"HELLO"}'


async def test_replacing_a_default(make_app, client_for):
    app = make_app(controllers=[ShoutController])
    app.response_serializers.replace(JsonSerializer, ShoutingJson())
    async with client_for(app) as client:
        res = await client.get("/shout/")
    assert res.text == '{"WORD":"HELLO"}'
