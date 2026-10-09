from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from patera import HttpMethod, MediaType, Request, Response
from patera.apiinterface import (
    ApiInterface,
    AuthType,
    MissingApiInterfaceConfigurations,
    auth,
    consumes,
    headers,
    method,
    no_auth,
    produces,
    resource,
    service,
    timeout,
)
from patera.apiinterface import api_interface as api_module
from patera.controller import Controller, get, path
from patera.injectable import Inject

pytestmark = pytest.mark.integration


class Repo(BaseModel):
    id: int
    name: str


@service("GITHUB_URL")
@auth(AuthType.BEARER, token="GITHUB_TOKEN")
@headers({"X-Client": "patera"})
@timeout(5)
class GithubApi(ApiInterface):
    @method(HttpMethod.GET)
    @resource("/repos/<repo_id>")
    async def get_repo(self) -> Repo: ...

    @method(HttpMethod.POST)
    @resource("/repos")
    @headers({"X-Client": "override"})
    async def create_repo(self, name: str, private: bool) -> dict: ...

    @method(HttpMethod.POST)
    @resource("/upload")
    @consumes(MediaType.APPLICATION_X_WWW_FORM_URLENCODED)
    @no_auth
    async def upload(self, data: dict) -> dict: ...

    @method(HttpMethod.DELETE)
    @resource("/repos/1")
    async def remove(self) -> dict: ...

    @method(HttpMethod.GET)
    @resource("/readme")
    @produces(MediaType.TEXT_PLAIN)
    async def readme(self) -> str: ...


@path("/proxy")
class ProxyController(Controller):
    github: Inject[GithubApi]

    @get("/repos/<int:repo_id>")
    async def repo(self, req: Request, repo_id: int) -> Response:
        repo = await self.github.get_repo()
        return req.res.json(repo)


@pytest.fixture
def requests_seen(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/repos/7":
            return httpx.Response(200, json={"id": 7, "name": "patera"})
        if request.url.path == "/repos/1":
            return httpx.Response(204)
        if request.url.path == "/readme":
            return httpx.Response(200, text="# Readme")
        return httpx.Response(200, json={"echo": request.content.decode()})

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(api_module.httpx, "AsyncClient", client_factory)
    return seen


@pytest.fixture
def app(make_app):
    return make_app(
        controllers=[ProxyController],
        GITHUB_URL="https://api.example.com",
        GITHUB_TOKEN="secret-token",
    )


async def test_get_inside_request_uses_route_params(app, client_for, requests_seen):
    async with client_for(app) as client:
        res = await client.get("/proxy/repos/7?page=2")
        assert res.json() == {"id": 7, "name": "patera"}
    sent = requests_seen[0]
    assert str(sent.url) == "https://api.example.com/repos/7?page=2"
    assert sent.headers["authorization"] == "Bearer secret-token"
    assert sent.headers["x-client"] == "patera"
    assert sent.headers["accept"] == "application/json"


async def test_calls_outside_request_context(app, requests_seen):
    api = (
        app.get_extension(GithubApi)
        if "GITHUB_API" in app.extensions
        else GithubApi(app)
    )

    result = await api.create_repo("new", private=True)
    assert json.loads(result["echo"]) == {"name": "new", "private": True}
    assert requests_seen[-1].headers["x-client"] == "override"

    await api.upload({"field": "value"})
    upload = requests_seen[-1]
    assert upload.content == b"field=value"
    assert "authorization" not in upload.headers

    assert await api.remove() is None  # empty 204 body
    assert await api.readme() == "# Readme"


def test_missing_service_url(make_app):
    class NoService(ApiInterface):
        pass

    app = make_app()
    with pytest.raises(MissingApiInterfaceConfigurations):
        NoService(app)


def test_auth_decorator_validation():
    with pytest.raises(ValueError):
        auth(AuthType.BASIC_AUTH, username="only-user")
    with pytest.raises(ValueError):
        auth(AuthType.BEARER)
    with pytest.raises(ValueError):
        auth(AuthType.API_KEY)
