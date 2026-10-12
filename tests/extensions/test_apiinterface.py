from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from patera import HttpMethod, MediaType, Request, Response
from typing import Optional

from patera.apiinterface import (
    ApiInterface,
    AuthType,
    ApiInterfaceResponseError,
    MissingApiInterfaceConfigurations,
    auth,
    consumes,
    forward_request,
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


class SearchFilters(BaseModel):
    q: str
    language: Optional[str] = None
    tags: list[str] = []


@service("GITHUB_URL")
@auth(AuthType.BEARER, token="GITHUB_TOKEN")
@headers({"X-Client": "patera"})
@timeout(5)
class GithubApi(ApiInterface):
    @method(HttpMethod.GET)
    @resource("/repos/<repo_id>")
    @forward_request
    async def get_repo(self) -> Repo: ...

    @method(HttpMethod.GET)
    @resource("/repos/<repo_id>")
    async def repo_by_id(self, repo_id: int) -> Repo: ...

    @method(HttpMethod.GET)
    @resource("/search/<int:owner>")
    async def search(self, owner: str, q: str, page: Optional[int] = None) -> dict: ...

    @method(HttpMethod.GET)
    @resource("/search/all")
    async def search_with_model(self, filters: SearchFilters) -> dict: ...

    @method(HttpMethod.PUT)
    @resource("/repos/<repo_id>")
    async def rename(self, repo_id: int, name: str) -> dict: ...

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

    @method(HttpMethod.GET)
    @resource("/missing")
    async def missing(self) -> Repo: ...

    @method(HttpMethod.GET)
    @resource("/broken")
    async def broken(self) -> dict: ...

    @method(HttpMethod.GET)
    @resource("/missing")
    async def missing_raw(self) -> httpx.Response: ...

    @method(HttpMethod.GET)
    @resource("/events")
    @produces(MediaType.APPLICATION_X_NDJSON)
    async def events(self) -> list: ...


@path("/proxy")
class ProxyController(Controller):
    github: Inject[GithubApi]

    @get("/repos/<int:repo_id>")
    async def repo(self, req: Request, repo_id: int) -> Response:
        repo = await self.github.get_repo()
        return req.res.json(repo)

    @get("/explicit/<int:repo_id>")
    async def explicit(self, req: Request, repo_id: int) -> Response:
        repo = await self.github.repo_by_id(repo_id)
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
        if request.url.path == "/missing":
            return httpx.Response(404, json={"message": "no such repo"})
        if request.url.path == "/broken":
            return httpx.Response(502, text="<html>Bad gateway</html>")
        if request.url.path == "/events":
            return httpx.Response(200, text='{"n": 1}\n{"n": 2}\n')
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


async def test_forward_request_uses_route_params(app, client_for, requests_seen):
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


async def test_requests_are_not_forwarded_by_default(app, client_for, requests_seen):
    async with client_for(app) as client:
        res = await client.get("/proxy/explicit/7?page=2")
        assert res.json() == {"id": 7, "name": "patera"}
    # The placeholder comes from the argument; the query string stays behind.
    assert str(requests_seen[0].url) == "https://api.example.com/repos/7"


async def test_placeholders_and_query_from_arguments(app, requests_seen):
    api = GithubApi(app)
    await api.search("ann/marie", "web framework", page=None)
    sent = requests_seen[-1]
    assert sent.url.raw_path == b"/search/ann%2Fmarie?q=web+framework"
    await api.search(owner="bo", q="x", page=2)
    assert requests_seen[-1].url.params == httpx.QueryParams({"q": "x", "page": "2"})
    assert requests_seen[-1].content == b""


async def test_model_argument_supplies_query_parameters(app, requests_seen):
    api = GithubApi(app)
    await api.search_with_model(SearchFilters(q="orm", tags=["a", "b"]))
    params = requests_seen[-1].url.params
    assert params.get("q") == "orm"
    assert params.get_list("tags") == ["a", "b"]
    assert "language" not in params


async def test_placeholder_arguments_leave_the_body(app, requests_seen):
    api = GithubApi(app)
    result = await api.rename(3, name="renamed")
    sent = requests_seen[-1]
    assert sent.url.path == "/repos/3"
    assert json.loads(result["echo"]) == "renamed"


async def test_missing_placeholder_value_is_an_error(app, requests_seen):
    api = GithubApi(app)
    with pytest.raises(MissingApiInterfaceConfigurations, match="<repo_id>"):
        await api.get_repo()  # forwarding, but no request to forward from
    assert requests_seen == []


forwarded_requests: list[httpx.Request] = []
created_clients: list[httpx.AsyncClient] = []


def _recording_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        forwarded_requests.append(request)
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


@service("https://api.example.com")
@forward_request
class Forwarding(ApiInterface):
    def create_client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=_recording_transport())
        created_clients.append(client)
        return client

    @method(HttpMethod.GET)
    @resource("/items/<item_id>")
    async def item(self, lang: Optional[str] = None) -> dict: ...

    @method(HttpMethod.GET)
    @resource("/static")
    @forward_request(False)
    async def static(self) -> dict: ...


@path("/items")
class Items(Controller):
    api: Inject[Forwarding]

    @get("/<int:item_id>")
    async def item(self, req: Request, item_id: int) -> Response:
        await self.api.item(lang="sl")
        await self.api.static()
        return req.res.json({})


@pytest.fixture
def forwarding_app(make_app):
    forwarded_requests.clear()
    created_clients.clear()
    return make_app(controllers=[Items])


async def test_forward_request_on_the_class_and_opt_out(forwarding_app, client_for):
    async with client_for(forwarding_app) as client:
        await client.get("/items/5?lang=en&page=3")
    forwarded, not_forwarded = forwarded_requests
    assert forwarded.url.path == "/items/5"
    # The method's own argument wins over the forwarded value.
    assert forwarded.url.params == httpx.QueryParams({"lang": "sl", "page": "3"})
    assert str(not_forwarded.url) == "https://api.example.com/static"


async def test_one_client_is_reused_and_closed_at_shutdown(forwarding_app, client_for):
    async with client_for(forwarding_app) as client:
        for _ in range(3):
            await client.get("/items/1")
        assert len(forwarded_requests) == 6
        assert len(created_clients) == 1
        assert not created_clients[0].is_closed
    assert created_clients[0].is_closed
    assert forwarding_app.get_extension(Forwarding)._client is None


def test_a_new_event_loop_gets_a_new_client(make_app):
    import asyncio

    created: list[httpx.AsyncClient] = []

    @service("https://api.example.com")
    class PerLoop(ApiInterface):
        def create_client(self) -> httpx.AsyncClient:
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
            )
            created.append(client)
            return client

        @method(HttpMethod.GET)
        @resource("/ping")
        async def ping(self) -> dict: ...

    api = PerLoop(make_app())
    asyncio.run(api.ping())
    asyncio.run(api.ping())  # e.g. two CLI commands
    assert len(created) == 2


async def test_error_statuses_raise(app, requests_seen):
    api = GithubApi(app)
    with pytest.raises(ApiInterfaceResponseError) as exc:
        await api.missing()
    assert exc.value.status_code == 404
    assert exc.value.body == {"message": "no such repo"}
    assert "GET https://api.example.com/missing answered 404" in str(exc.value)

    with pytest.raises(ApiInterfaceResponseError) as exc:
        await api.broken()
    assert exc.value.status_code == 502
    assert exc.value.body == "<html>Bad gateway</html>"  # not JSON: raw text


async def test_raw_response_annotation_skips_the_status_check(app, requests_seen):
    response = await GithubApi(app).missing_raw()
    assert isinstance(response, httpx.Response)
    assert response.status_code == 404


async def test_ndjson_responses_are_parsed_line_by_line(app, requests_seen):
    assert await GithubApi(app).events() == [{"n": 1}, {"n": 2}]
