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


# ---- JSON encoding of common Python values ----------------------------------

import datetime as _dt  # noqa: E402
import decimal as _decimal  # noqa: E402
import uuid as _uuid  # noqa: E402

from pydantic import BaseModel as _BaseModel  # noqa: E402

from patera.serializers import json_bytes, ndjson_line  # noqa: E402


class _Row(_BaseModel):
    name: str


def test_json_encodes_models_dates_uuids_and_decimals():
    value = {
        "rows": [_Row(name="a")],
        "when": _dt.datetime(2026, 1, 2, 3, 4),
        "day": _dt.date(2026, 1, 2),
        "id": _uuid.UUID(int=1),
        "price": _decimal.Decimal("1.50"),
        "text": "Šola",
    }
    assert (
        json_bytes(value)
        == (
            '{"rows":[{"name":"a"}],"when":"2026-01-02T03:04:00","day":"2026-01-02",'
            '"id":"00000000-0000-0000-0000-000000000001","price":"1.50","text":"Šola"}'
        ).encode()
    )


def test_declared_types_filter_lists_dicts_and_objects():
    secret_rows = [
        {"name": "a", "password_hash": "x"},
        {"name": "b", "password_hash": "y"},
    ]
    assert json_bytes(secret_rows, list[_Row]) == b'[{"name":"a"},{"name":"b"}]'
    assert json_bytes({"k": secret_rows[0]}, dict[str, _Row]) == b'{"k":{"name":"a"}}'

    class Orm:  # e.g. a SQLAlchemy model instance
        name = "c"
        password_hash = "z"

    assert json_bytes(Orm(), _Row) == b'{"name":"c"}'
    assert json_bytes(None, _Row | None) == b"null"


def test_ndjson_rows_use_the_same_encoding():
    assert ndjson_line({"day": _dt.date(2026, 1, 2)}) == '{"day":"2026-01-02"}\n'
    assert ndjson_line({"name": "a", "x": 1}, list[_Row]) == '{"name":"a"}\n'


async def test_declared_type_only_shapes_success_bodies(app):
    # Response[Out] describes the success body. Error bodies, such as the
    # 415 that @consumes returns, keep their own fields.
    error = {"status": "error", "message": "Unsupported media type", "data": {"x": 1}}
    ok = make_request(app).res.json(dict(error))
    assert await app.response_renderer.render_body(ok, _Message) == (
        b'{"message":"Unsupported media type"}'
    )
    failed = make_request(app).res.json(dict(error)).status(415)
    assert await app.response_renderer.render_body(failed, _Message) == (
        b'{"status":"error","message":"Unsupported media type","data":{"x":1}}'
    )


class _Message(_BaseModel):
    message: str


# ----- materialize ---------------------------------------------------------------


class _OrmRow:
    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name


class _OrmRowOut(_BaseModel):
    id: int
    name: str


def test_materialize_converts_objects_through_model_types():
    from patera.serializers import materialize

    rows = materialize([_OrmRow(1, "a")], list[_OrmRowOut])
    assert rows == [_OrmRowOut(id=1, name="a")]
    assert materialize(_OrmRow(2, "b"), _OrmRowOut) == _OrmRowOut(id=2, name="b")
    # Without a model in the type, or for raw bodies, nothing changes.
    plain = {"id": 1}
    assert materialize(plain, dict) is plain
    assert materialize(b"raw", _OrmRowOut) == b"raw"
    assert materialize(plain, None) is plain


async def test_materialize_body_skips_errors_streams_and_other_media(app):
    from patera.response_renderer import ResponseRendererException
    from tests.helpers import make_request

    renderer = app.response_renderer

    res = make_request(app).res.json([_OrmRow(1, "a")])
    renderer.materialize_body(res, list[_OrmRowOut])
    assert res.body == [_OrmRowOut(id=1, name="a")]

    error = make_request(app).res.json({"message": "nope"}).status(HttpStatus.NOT_FOUND)
    renderer.materialize_body(error, _OrmRowOut)
    assert error.body == {"message": "nope"}

    text = make_request(app).res.text("hello")
    renderer.materialize_body(text, _OrmRowOut)
    assert text.body == "hello"

    bad = make_request(app).res.json({"id": "x", "name": "a"})
    with pytest.raises(ResponseRendererException):
        renderer.materialize_body(bad, _OrmRowOut)
