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
    assert await registry.serialize(res) == b'{"a":1}\n{"id":1,"name":"x"}\n'


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


class Marker:
    """A serializer that claims every response."""

    def can_serialize(self, response) -> bool:
        return True

    async def serialize(self, response, response_type=None) -> bytes:
        return b"marker"


async def test_register_appends_by_default(app, registry):
    registry.register(Marker())
    assert isinstance(registry.serializers[-1], Marker)
    # The JSON serializer still claims JSON bodies first.
    res = make_request(app).res.json({"a": 1})
    assert await registry.serialize(res) == b'{"a":1}'


async def test_register_first_takes_precedence(app, registry):
    registry.register(Marker(), first=True)
    assert isinstance(registry.serializers[0], Marker)
    res = make_request(app).res.json({"a": 1})
    assert await registry.serialize(res) == b"marker"


async def test_replace_and_unregister(app, registry):
    from patera.serializers import JsonSerializer, StringSerializer

    position = [type(s) for s in registry.serializers].index(JsonSerializer)
    registry.replace(JsonSerializer, Marker())
    assert isinstance(registry.serializers[position], Marker)
    with pytest.raises(LookupError):
        registry.replace(JsonSerializer, Marker())

    registry.unregister(StringSerializer)
    assert StringSerializer not in [type(s) for s in registry.serializers]


async def test_ndjson_rows_use_the_item_model_of_a_list_annotation(app, registry):
    res = make_request(app).res.ndjson([{"id": "1", "name": "a", "extra": True}])
    assert await registry.serialize(res, list[User]) == b'{"id":1,"name":"a"}\n'
