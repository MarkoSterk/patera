"""
Headers[Model] and Cookies[Model] handler parameters: name mapping, aliases,
repeated headers, validation errors, registration errors and OpenAPI.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import pytest
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from patera import MediaType, Request, Response
from patera.controller import (
    Controller,
    Cookies,
    Headers,
    QueryParams,
    RequestBody,
    consumes,
    get,
    path,
    post,
    produces,
    socket,
)
from patera.controller.params import handler_params


class ClientHeaders(BaseModel):
    # Only declared headers are passed in, so extras can be forbidden.
    model_config = ConfigDict(extra="forbid")

    api_version: int = Field(alias="X-Api-Version")
    x_request_id: Optional[UUID] = None
    client_ip: str = Field(default="unknown", alias="X-Forwarded-For")
    accept_language: list[str] = []


class SessionCookies(BaseModel):
    session_id: str
    token: Optional[str] = Field(default=None, alias="__Host-token")
    visits: int = 0


class AuthHeaders(BaseModel):
    authorization: str
    x_tenant: str


class Paging(BaseModel):
    page: int = 1


class Note(BaseModel):
    text: str


@path("/meta")
class MetaController(Controller):
    @get("/headers")
    @produces(MediaType.APPLICATION_JSON)
    async def headers(self, req: Request, meta: Headers[ClientHeaders]) -> Response:
        return req.res.json(meta.model_dump(mode="json"))

    @get("/cookies")
    @produces(MediaType.APPLICATION_JSON)
    async def cookies(self, req: Request, jar: Cookies[SessionCookies]) -> Response:
        return req.res.json(jar.model_dump(mode="json"))

    @post("/notes")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def create(
        self,
        req: Request,
        data: RequestBody[Note],
        paging: QueryParams[Paging],
        meta: Headers[ClientHeaders],
        jar: Cookies[SessionCookies],
    ) -> Response:
        return req.res.json(
            {
                "text": data.text,
                "page": paging.page,
                "version": meta.api_version,
                "session": jar.session_id,
            }
        )

    @get("/auth")
    @produces(MediaType.APPLICATION_JSON)
    async def auth(self, req: Request, meta: Headers[AuthHeaders]) -> Response:
        return req.res.json(meta.model_dump())


@pytest.fixture
def app(make_app):
    return make_app(controllers=[MetaController])


def test_plan_maps_fields_to_http_names():
    plan = handler_params(MetaController.headers)
    assert [p.name for p in plan.headers] == ["meta"]
    assert plan.headers[0].names == (
        ("X-Api-Version", "x-api-version", False),
        ("x_request_id", "x-request-id", False),
        ("X-Forwarded-For", "x-forwarded-for", False),
        ("accept_language", "accept-language", True),
    )
    cookies = handler_params(MetaController.cookies).cookies[0]
    assert cookies.names == (
        ("session_id", "session_id", False),
        ("__Host-token", "__Host-token", False),
        ("visits", "visits", False),
    )


async def test_headers_are_matched_by_name_and_alias(app, client_for):
    async with client_for(app) as client:
        res = await client.get(
            "/meta/headers",
            headers={
                # Header names are matched without regard to case.
                "X-API-VERSION": "2",
                "X-Request-Id": "12345678-1234-5678-1234-567812345678",
                "x-forwarded-for": "10.0.0.1",
            },
        )
        assert res.status_code == 200, res.text
        assert res.json() == {
            "api_version": 2,
            "x_request_id": "12345678-1234-5678-1234-567812345678",
            "client_ip": "10.0.0.1",
            "accept_language": [],
        }


async def test_a_list_field_receives_every_header_line(app, client_for):
    async with client_for(app) as client:
        res = await client.get(
            "/meta/headers",
            headers=[
                ("X-Api-Version", "1"),
                ("Accept-Language", "en"),
                ("Accept-Language", "sl, de"),
            ],
        )
        assert res.json()["accept_language"] == ["en", "sl, de"]


async def test_header_errors_name_the_header(app, client_for):
    async with client_for(app) as client:
        missing = await client.get("/meta/headers")
        assert missing.status_code == 422
        assert missing.json()["data"][0]["loc"] == ["header", "x-api-version"]

        bad = await client.get(
            "/meta/headers",
            headers={"X-Api-Version": "two", "X-Request-Id": "not-a-uuid"},
        )
        assert bad.status_code == 422
        locs = {tuple(error["loc"]) for error in bad.json()["data"]}
        assert locs == {("header", "x-api-version"), ("header", "x-request-id")}


async def test_cookies_are_matched_by_exact_name(app, client_for):
    async with client_for(app) as client:
        res = await client.get(
            "/meta/cookies",
            headers={"cookie": "session_id=abc; __Host-token=t0k; visits=3; other=x"},
        )
        assert res.status_code == 200, res.text
        assert res.json() == {"session_id": "abc", "token": "t0k", "visits": 3}

        wrong_case = await client.get(
            "/meta/cookies", headers={"cookie": "Session_Id=abc"}
        )
        assert wrong_case.status_code == 422
        assert wrong_case.json()["data"][0]["loc"] == ["cookie", "session_id"]

        bad = await client.get(
            "/meta/cookies", headers={"cookie": "session_id=abc; visits=many"}
        )
        assert bad.status_code == 422
        assert bad.json()["data"][0]["loc"] == ["cookie", "visits"]


async def test_all_sources_together(app, client_for):
    async with client_for(app) as client:
        res = await client.post(
            "/meta/notes?page=4",
            json={"text": "hello"},
            headers={"X-Api-Version": "3", "cookie": "session_id=s1"},
        )
        assert res.status_code == 200, res.text
        assert res.json() == {"text": "hello", "page": 4, "version": 3, "session": "s1"}


# --- Registration errors -------------------------------------------------------


def _controller(method):
    return path("/broken")(type("BrokenController", (Controller,), {"m": method}))


@pytest.mark.parametrize("annotation", ["Headers[str]", "Cookies[dict[str, str]]"])
def test_markers_need_a_model(annotation):
    async def m(self, req: Request, value) -> Response: ...

    m.__annotations__["value"] = annotation
    with pytest.raises(TypeError, match="needs a Pydantic model"):
        handler_params(m)


class ChoiceHeaders(BaseModel):
    trace: str = Field(validation_alias=AliasChoices("traceparent", "x-trace"))


def test_aliases_must_be_plain_strings():
    async def m(self, req: Request, meta: Headers[ChoiceHeaders]) -> Response: ...

    with pytest.raises(TypeError, match="plain string alias"):
        handler_params(m)


class TwiceHeaders(BaseModel):
    x_trace: str = ""
    trace: str = Field(default="", alias="X-Trace")


def test_two_fields_cannot_read_the_same_header():
    async def m(self, req: Request, meta: Headers[TwiceHeaders]) -> Response: ...

    with pytest.raises(TypeError, match="both read the header 'x-trace'"):
        handler_params(m)


def test_socket_handlers_reject_headers(make_app):
    @socket("/ws")
    async def m(self, req: Request, meta: Headers[ClientHeaders]) -> None: ...

    with pytest.raises(TypeError, match="WebSocket"):
        make_app(controllers=[_controller(m)])


# --- OpenAPI -------------------------------------------------------------------


def test_openapi_header_and_cookie_parameters(make_app):
    spec = make_app(controllers=[MetaController]).json_spec
    params = spec["paths"]["/meta/headers"]["get"]["parameters"]
    by_name = {p["name"]: p for p in params}
    assert set(by_name) == {
        "x-api-version",
        "x-request-id",
        "x-forwarded-for",
        "accept-language",
    }
    assert all(p["in"] == "header" for p in params)
    assert by_name["x-api-version"]["required"] is True
    assert by_name["x-api-version"]["schema"]["type"] == "integer"
    assert by_name["accept-language"]["schema"]["type"] == "array"

    cookie_params = spec["paths"]["/meta/cookies"]["get"]["parameters"]
    assert {(p["name"], p["in"], p["required"]) for p in cookie_params} == {
        ("session_id", "cookie", True),
        ("__Host-token", "cookie", False),
        ("visits", "cookie", False),
    }

    combined = spec["paths"]["/meta/notes"]["post"]["parameters"]
    assert {p["in"] for p in combined} == {"query", "header", "cookie"}

    # OpenAPI ignores an Authorization header parameter; it is left out.
    auth = spec["paths"]["/meta/auth"]["get"]["parameters"]
    assert [p["name"] for p in auth] == ["x-tenant"]
