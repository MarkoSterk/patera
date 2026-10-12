"""
Error responses produced by the framework itself: their shape, and the CORS
headers on errors raised before the middleware chain runs.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from patera import MediaType, Request, Response
from patera.controller import Controller, consumes, get, path, post

pytestmark = pytest.mark.integration

ORIGIN = "https://app.example"


class Item(BaseModel):
    name: str


@path("/api")
class ItemsController(Controller):
    @get("/items/")
    async def items(self, req: Request) -> Response:
        return req.res.json([])

    @post("/items/")
    @consumes(MediaType.APPLICATION_JSON)
    async def create(self, req: Request, item: Item) -> Response:
        return req.res.json(item.model_dump()).status(201)

    @post("/raw")
    async def raw(self, req: Request) -> Response:
        return req.res.json({"received": await req.json()})


@pytest.fixture
def app(make_app):
    return make_app(
        controllers=[ItemsController],
        CORS_ALLOW_ORIGINS=[ORIGIN],
        DEBUG=False,
    )


def _assert_error_shape(res, status: int, message: str) -> dict:
    assert res.status_code == status
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert body["status"] == "error"
    assert body["message"] == message
    return body


# ---- Malformed JSON ----------------------------------------------------------


async def test_malformed_json_with_consumes_is_400(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/items/",
            content=b'{"name": ',
            headers={"content-type": "application/json"},
        )
    body = _assert_error_shape(res, 400, "Malformed JSON body")
    assert "detail" in body["data"]


async def test_malformed_json_read_in_handler_is_400(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/raw",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
    _assert_error_shape(res, 400, "Malformed JSON body")


async def test_valid_json_still_works(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/api/items/", json={"name": "lamp"})
        assert res.status_code == 201
        assert res.json() == {"name": "lamp"}
        res = await client.post("/api/raw", json=[1, 2])
        assert res.json() == {"received": [1, 2]}


async def test_missing_fields_are_still_422(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/api/items/", json={})
    assert res.status_code == 422
    assert res.json()["errors"]


# ---- Shapes of framework errors ---------------------------------------------


async def test_not_found_shape(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/nowhere")
    _assert_error_shape(res, 404, "Endpoint not found")


async def test_method_not_allowed_shape(app, client_for):
    async with client_for(app) as client:
        res = await client.delete("/api/items/")
    body = _assert_error_shape(res, 405, "Method not allowed")
    # Werkzeug adds HEAD wherever GET is allowed.
    assert set(body["data"]["allowed_methods"]) == {"GET", "HEAD", "POST"}
    assert {m.strip() for m in res.headers["allow"].split(",")} == {
        "GET",
        "HEAD",
        "POST",
    }


async def test_unsupported_media_type_shape(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/api/items/", content=b"name=x", headers={"content-type": "text/plain"}
        )
    body = _assert_error_shape(res, 415, "Unsupported media type")
    assert body["data"] == {
        "expected": "application/json",
        "received": "text/plain",
    }


async def test_bad_request_shape(app):
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    await app.abort_bad_request(send)
    assert sent[0]["status"] == 400
    assert b'"message": "Bad request"' in sent[1]["body"]


async def test_preflight_with_disallowed_method_is_json(make_app, client_for):
    app = make_app(
        controllers=[ItemsController],
        CORS_ALLOW_ORIGINS=[ORIGIN],
        CORS_ALLOW_METHODS=["GET"],
    )
    async with client_for(app) as client:
        res = await client.options(
            "/api/items/",
            headers={"origin": ORIGIN, "access-control-request-method": "POST"},
        )
    _assert_error_shape(res, 405, "Preflight method not allowed")


# ---- CORS on routing errors ---------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url", "status"),
    [("GET", "/nowhere", 404), ("DELETE", "/api/items/", 405)],
)
async def test_routing_errors_carry_cors_headers(app, client_for, method, url, status):
    async with client_for(app) as client:
        res = await client.request(method, url, headers={"origin": ORIGIN})
    assert res.status_code == status
    assert res.headers["access-control-allow-origin"] == ORIGIN
    assert res.headers["access-control-allow-credentials"] == "true"


async def test_routing_errors_skip_cors_for_disallowed_origin(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/nowhere", headers={"origin": "https://evil.example"})
    assert res.status_code == 404
    assert "access-control-allow-origin" not in res.headers


async def test_routing_errors_without_origin_have_no_cors(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/nowhere")
    assert "access-control-allow-origin" not in res.headers


async def test_routing_errors_without_cors_enabled(make_app, client_for):
    app = make_app(controllers=[ItemsController], CORS_ENABLED=False)
    async with client_for(app) as client:
        res = await client.get("/nowhere", headers={"origin": ORIGIN})
    assert res.status_code == 404
    assert "access-control-allow-origin" not in res.headers


async def test_trailing_slash_redirect_carries_cors(make_app, client_for):
    app = make_app(
        controllers=[ItemsController],
        CORS_ALLOW_ORIGINS=[ORIGIN],
        STRICT_SLASHES=True,
    )
    async with client_for(app) as client:
        res = await client.get("/api/items", headers={"origin": ORIGIN})
    assert res.status_code in (301, 308)
    assert res.headers["location"].endswith("/api/items/")
    assert res.headers["access-control-allow-origin"] == ORIGIN
