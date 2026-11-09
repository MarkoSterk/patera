"""
Headers, Cookies and QueryParams parameters on middleware methods and
@before_request hooks.
"""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel, Field

from patera import MediaType, MiddlewareBase, Request, Response
from patera.controller import (
    Controller,
    Cookies,
    Headers,
    QueryParams,
    RequestBody,
    after_request,
    before_request,
    get,
    path,
    produces,
)
from patera.middleware import middleware


class TenantHeaders(BaseModel):
    x_tenant: str
    x_trace: Optional[str] = None


class Locale(BaseModel):
    lang: str = Field(default="en", pattern="^[a-z]{2}$")


class Theme(BaseModel):
    theme: str = "light"


class Debug(BaseModel):
    debug: bool = False


@middleware(order=10)
class TenantMiddleware(MiddlewareBase):
    async def middleware(
        self,
        req: Request,
        tenant: Headers[TenantHeaders],
        prefs: Cookies[Theme],
        flags: QueryParams[Debug],
    ) -> Response:
        req.context.set("tenant", tenant.x_tenant)
        req.context.set("theme", prefs.theme)
        req.context.set("debug", flags.debug)
        return await self.next(req)


@middleware(order=20)
class SyncTraceMiddleware(MiddlewareBase):
    # Synchronous middleware methods receive their parameters too.
    open_api_spec = False

    def middleware(self, req: Request, tenant: Headers[TenantHeaders]):
        req.context.set("trace", tenant.x_trace)
        return self.next(req)


@middleware(order=30)
class PlainMiddleware(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        req.context.set("plain", True)
        return await self.next(req)


@path("/hooks")
class HookedController(Controller):
    @before_request
    async def remember_locale(self, req: Request, locale: QueryParams[Locale]) -> None:
        req.context.set("lang", locale.lang)

    @before_request
    def plain(self, req: Request) -> None:
        req.context.set("plain_hook", True)

    @after_request
    def mark(self, res: Response) -> None:
        res.set_header("x-after", "yes")

    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def index(self, req: Request) -> Response:
        ctx = req.context
        return req.res.json(
            {
                key: ctx.get(key)
                for key in (
                    "tenant",
                    "theme",
                    "debug",
                    "trace",
                    "plain",
                    "lang",
                    "plain_hook",
                )
            }
        )

    @get("/override")
    @produces(MediaType.APPLICATION_JSON)
    async def override(self, req: Request, locale: QueryParams[Locale]) -> Response:
        return req.res.json({"lang": locale.lang})


@path("/other")
class OtherController(Controller):
    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def index(self, req: Request) -> Response:
        return req.res.json({"ok": True})


@pytest.fixture
def app(make_app):
    return make_app(
        controllers=[HookedController, OtherController],
        middleware=[TenantMiddleware, SyncTraceMiddleware, PlainMiddleware],
    )


async def test_middleware_and_hooks_receive_their_parameters(app, client_for):
    async with client_for(app) as client:
        res = await client.get(
            "/hooks/?lang=sl&debug=true",
            headers={"X-Tenant": "acme", "X-Trace": "t1", "cookie": "theme=dark"},
        )
        assert res.status_code == 200, res.text
        assert res.json() == {
            "tenant": "acme",
            "theme": "dark",
            "debug": True,
            "trace": "t1",
            "plain": True,
            "lang": "sl",
            "plain_hook": True,
        }


async def test_middleware_validation_errors_are_422(app, client_for):
    async with client_for(app) as client:
        missing = await client.get("/other/")
        assert missing.status_code == 422
        assert missing.json()["data"][0]["loc"] == ["header", "x-tenant"]

        bad_query = await client.get("/other/?debug=perhaps", headers={"X-Tenant": "a"})
        assert bad_query.status_code == 422
        assert bad_query.json()["data"][0]["loc"] == ["query", "debug"]


async def test_hook_validation_error_stops_before_the_endpoint(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/hooks/?lang=english", headers={"X-Tenant": "a"})
        assert res.status_code == 422
        assert res.json()["data"][0]["loc"] == ["query", "lang"]
        # As for any exception, after-request hooks are skipped.
        assert "x-after" not in res.headers

        # Hooks of one controller do not run for another.
        other = await client.get("/other/?lang=english", headers={"X-Tenant": "a"})
        assert other.status_code == 200


# --- Startup errors ------------------------------------------------------------


def _build(make_app, middleware_class):
    app = make_app(middleware=[middleware_class])
    app.build()


def test_middleware_rejects_parameters_nothing_fills(make_app):
    @middleware(order=10)
    class Retrying(MiddlewareBase):
        async def middleware(self, req: Request, retries: int = 3) -> Response:
            return await self.next(req)

    with pytest.raises(TypeError, match="nothing fills the parameter 'retries'"):
        _build(make_app, Retrying)


def test_middleware_rejects_unmarked_models(make_app):
    @middleware(order=10)
    class Unmarked(MiddlewareBase):
        async def middleware(self, req: Request, tenant: TenantHeaders) -> Response:
            return await self.next(req)

    with pytest.raises(TypeError, match="nothing fills the parameter 'tenant'"):
        _build(make_app, Unmarked)


def test_middleware_rejects_bodies(make_app):
    @middleware(order=10)
    class Body(MiddlewareBase):
        async def middleware(self, req: Request, data: RequestBody[Locale]) -> Response:
            return await self.next(req)

    with pytest.raises(TypeError, match="only available on endpoints"):
        _build(make_app, Body)


def test_before_request_hooks_are_checked_at_registration(make_app):
    @path("/broken")
    class Broken(Controller):
        @before_request
        def hook(self, req: Request, attempts: int = 1) -> None: ...

        @get("/")
        async def index(self, req: Request) -> Response:
            return req.res.json({})

    with pytest.raises(TypeError, match=r"Broken.hook \(@before_request\)"):
        make_app(controllers=[Broken])


async def test_middleware_without_super_init_still_works(make_app, client_for):
    @middleware(order=10)
    class CustomInit(MiddlewareBase):
        def __init__(self, app, next_app):
            self._app = app
            self._next = next_app

        async def middleware(self, req: Request, tenant: Headers[TenantHeaders]):
            req.context.set("tenant", tenant.x_tenant)
            return await self.next(req)

    app = make_app(controllers=[HookedController], middleware=[CustomInit])
    async with client_for(app) as client:
        res = await client.get("/hooks/", headers={"X-Tenant": "acme"})
        assert res.json()["tenant"] == "acme"


# --- OpenAPI -------------------------------------------------------------------


def test_openapi_includes_hook_and_middleware_parameters(app):
    spec = app.json_spec

    def params(path_name):
        return {
            (p["in"], p["name"]) for p in spec["paths"][path_name]["get"]["parameters"]
        }

    middleware_params = {
        ("header", "x-tenant"),
        ("header", "x-trace"),
        ("cookie", "theme"),
        ("query", "debug"),
    }
    # Middleware parameters apply to every operation; hook parameters to the
    # hook's controller only. SyncTraceMiddleware opted out (open_api_spec).
    assert params("/hooks/") == middleware_params | {("query", "lang")}
    assert params("/other/") == middleware_params

    # The endpoint's own parameter comes first and is not repeated.
    override = spec["paths"]["/hooks/override"]["get"]["parameters"]
    assert [p["name"] for p in override].count("lang") == 1
    assert override[0]["name"] == "lang"
