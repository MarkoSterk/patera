from __future__ import annotations

import pytest

from patera import Request, Response
from patera.controller import Controller, cors, get, no_cors, path, post

pytestmark = pytest.mark.integration


@path("/api")
class CorsController(Controller):
    @get("/items")
    async def items(self, req: Request) -> Response:
        return req.res.json([])

    @post("/items")
    async def create(self, req: Request) -> Response:
        raise KeyError("boom")  # unhandled -> 500 in production

    @get("/private")
    @no_cors
    async def private(self, req: Request) -> Response:
        return req.res.text("private")

    @get("/partner")
    @cors(
        allow_origins=["https://partner.example"], allow_credentials=False, max_age=600
    )
    async def partner(self, req: Request) -> Response:
        return req.res.text("partner")


@pytest.fixture
def app(make_app):
    return make_app(
        controllers=[CorsController],
        CORS_ALLOW_ORIGINS=["https://app.example"],
        CORS_EXPOSE_HEADERS=["x-total"],
        DEBUG=False,
    )


async def test_preflight(app, client_for):
    async with client_for(app) as client:
        for url in ("/api/items", "/api/items/"):
            res = await client.options(
                url,
                headers={
                    "origin": "https://app.example",
                    "access-control-request-method": "POST",
                    "access-control-request-headers": "content-type",
                },
            )
            assert res.status_code == 204
            assert res.headers["access-control-allow-origin"] == "https://app.example"
            assert "POST" in res.headers["access-control-allow-methods"]
            # Credentials are off unless the application turns them on.
            assert "access-control-allow-credentials" not in res.headers


async def test_preflight_from_disallowed_origin(app, client_for):
    async with client_for(app) as client:
        res = await client.options(
            "/api/items",
            headers={
                "origin": "https://evil.example",
                "access-control-request-method": "GET",
            },
        )
        assert res.status_code == 403


async def test_actual_request_headers(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/api/items", headers={"origin": "https://app.example"})
        assert res.status_code == 200
        assert res.headers["access-control-allow-origin"] == "https://app.example"
        assert res.headers["access-control-expose-headers"] == "x-total"
        assert res.headers["vary"] == "Origin"


async def test_error_responses_also_carry_cors_headers(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/api/items", headers={"origin": "https://app.example"})
        assert res.status_code == 500
        assert res.headers["access-control-allow-origin"] == "https://app.example"


async def test_disallowed_origin_passes_through_without_headers(app, client_for):
    # Same-origin form posts also send an Origin header; they must not be blocked.
    async with client_for(app) as client:
        res = await client.get(
            "/api/items", headers={"origin": "https://other.example"}
        )
        assert res.status_code == 200
        assert "access-control-allow-origin" not in res.headers


async def test_no_cors_and_endpoint_overrides(app, client_for):
    async with client_for(app) as client:
        res = await client.get(
            "/api/private", headers={"origin": "https://app.example"}
        )
        assert res.status_code == 200
        assert "access-control-allow-origin" not in res.headers

        res = await client.options(
            "/api/partner",
            headers={
                "origin": "https://partner.example",
                "access-control-request-method": "GET",
            },
        )
        assert res.status_code == 204
        assert res.headers["access-control-allow-origin"] == "https://partner.example"
        assert res.headers["access-control-max-age"] == "600"
        assert "access-control-allow-credentials" not in res.headers


async def test_cors_can_be_disabled(make_app, client_for):
    app = make_app(controllers=[CorsController], CORS_ENABLED=False)
    async with client_for(app) as client:
        res = await client.get("/api/items", headers={"origin": "https://app.example"})
        assert "access-control-allow-origin" not in res.headers
        res = await client.options(
            "/api/items",
            headers={
                "origin": "https://app.example",
                "access-control-request-method": "GET",
            },
        )
        assert res.status_code == 204
        assert "allow" in res.headers


async def test_credentials_are_off_by_default_and_can_be_enabled(make_app, client_for):
    default = make_app(controllers=[CorsController])
    async with client_for(default) as client:
        res = await client.get("/api/items", headers={"origin": "https://any.example"})
    # Any origin may read public responses, but no cookies are allowed.
    assert res.headers["access-control-allow-origin"] in ("*", "https://any.example")
    assert "access-control-allow-credentials" not in res.headers

    trusted = make_app(
        controllers=[CorsController],
        CORS_ALLOW_ORIGINS=["https://app.example"],
        CORS_ALLOW_CREDENTIALS=True,
    )
    async with client_for(trusted) as client:
        res = await client.get("/api/items", headers={"origin": "https://app.example"})
    assert res.headers["access-control-allow-origin"] == "https://app.example"
    assert res.headers["access-control-allow-credentials"] == "true"


async def test_every_cors_response_varies_by_origin(app, client_for):
    """
    Responses differ by Origin (with or without CORS headers), so a shared
    cache must key on it, also when the request has no Origin, comes from a
    refused origin, or ends in a routing error.
    """
    async with client_for(app) as client:
        for headers in (
            {},
            {"origin": "https://evil.example"},
            {"origin": "https://app.example"},
        ):
            res = await client.get("/api/items", headers=headers)
            assert res.headers.get_list("vary") == ["Origin"], headers
        missing = await client.get(
            "/api/missing", headers={"origin": "https://evil.example"}
        )
        assert missing.status_code == 404
        assert missing.headers.get("vary") == "Origin"
        preflight = await client.options(
            "/api/items",
            headers={
                "origin": "https://app.example",
                "access-control-request-method": "POST",
            },
        )
        assert preflight.headers.get_list("vary") == ["Origin"]
        # Routes without CORS do not vary.
        assert "vary" not in (await client.get("/api/private")).headers
