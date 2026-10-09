from __future__ import annotations

import pytest
from pydantic import BaseModel

from patera import HttpStatus
from patera.serializers import SerializerRegistry

from tests.helpers import make_request


class User(BaseModel):
    id: int
    name: str


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def registry():
    reg = SerializerRegistry()
    reg.register_defaults()
    return reg


async def test_json_dict(app, registry):
    res = make_request(app).res.json({"a": "č", "b": [1, 2]})
    assert await registry.serialize(res) == '{"a":"č","b":[1,2]}'.encode()


async def test_json_pydantic_model_and_response_type(app, registry):
    res = make_request(app).res.json(User(id=1, name="x"))
    assert await registry.serialize(res) == b'{"id":1,"name":"x"}'

    res = make_request(app).res.json({"id": "2", "name": "y", "extra": 1})
    assert await registry.serialize(res, User) == b'{"id":2,"name":"y"}'


async def test_ndjson(app, registry):
    res = make_request(app).res.ndjson([{"a": 1}, User(id=1, name="x")])
    assert await registry.serialize(res) == b'{"a":1}\n{"id":1,"name":"x"}'


async def test_text_and_bytes(app, registry):
    assert await registry.serialize(make_request(app).res.text("hi")) == b"hi"
    assert (
        await registry.serialize(make_request(app).res.bytes(b"\x00\x01"))
        == b"\x00\x01"
    )


async def test_no_content_drops_body(app, registry):
    res = make_request(app).res.json({"a": 1}).status(HttpStatus.NO_CONTENT)
    assert await registry.serialize(res) is None
    assert res.body is None


async def test_unknown_body_type_raises(app, registry):
    res = make_request(app).res
    res.body = object()
    res.media_type = "application/x-custom"
    with pytest.raises(TypeError):
        await registry.serialize(res)
