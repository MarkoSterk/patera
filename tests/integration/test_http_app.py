"""
End-to-end behaviour of the core framework through the ASGI interface.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from patera import HttpStatus, MediaType, Request, Response, abort, html_abort
from patera.controller import (
    Controller,
    after_request,
    before_request,
    consumes,
    delete,
    get,
    patch,
    path,
    post,
    produces,
    put,
)
from patera.exceptions import (
    BaseHttpException,
    ExceptionHandler,
    exception_handler,
    handles,
)
from patera.utilities import development, ignore

pytestmark = pytest.mark.integration


class NewUser(BaseModel):
    name: str
    age: int


class UserOut(BaseModel):
    id: int
    name: str


class Conflict(BaseHttpException):
    def __init__(self, message: str):
        super().__init__(message, HttpStatus.CONFLICT)


@path("/api/users", alias="users")
class UserController(Controller):
    calls: list[str]

    @before_request
    async def before(self, req: Request) -> None:
        req.context.set("before", True)

    @after_request
    def after(self, res: Response) -> None:
        res.set_header("x-after", "1")

    @get("/")
    async def list_users(self, req: Request) -> Response:
        return req.res.json({"before": req.context.get("before")})

    @get("/<int:user_id>")
    async def get_user(self, req: Request, user_id: int) -> Response[UserOut]:
        if user_id == 0:
            abort("User not found", HttpStatus.NOT_FOUND, data={"id": user_id})
        return req.res.json({"id": user_id, "name": "Ana", "secret": "x"})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    async def create(self, req: Request, user: NewUser) -> Response:
        return req.res.json(user)

    @put("/<int:user_id>")
    async def replace(self, req: Request, user_id: int) -> Response:
        return req.res.json({"method": "PUT", "id": user_id})

    @patch("/<int:user_id>")
    async def update(self, req: Request, user_id: int) -> Response:
        return req.res.json({"method": "PATCH", "id": user_id})

    @delete("/<int:user_id>")
    async def remove(self, req: Request, user_id: int) -> Response:
        return req.res.no_content()

    @get("/conflict")
    async def conflict(self, req: Request) -> Response:
        raise Conflict("Already exists")

    @get("/crash")
    async def crash(self, req: Request) -> Response:
        raise RuntimeError("unexpected")

    @get("/not-a-response")
    async def not_a_response(self, req: Request):
        return {"plain": "dict"}

    @get("/redirect")
    async def redirect(self, req: Request) -> Response:
        return req.res.redirect(req.app.url_for("users.get_user", user_id=7))

    @get("/page")
    async def page(self, req: Request) -> Response:
        return await req.res.html("page.html", {"title": "Hi"})

    @get("/html-abort")
    async def html_aborted(self, req: Request) -> Response:
        html_abort("error.html", HttpStatus.FORBIDDEN, {"reason": "nope"})

    @get("/sync")
    def sync_handler(self, req: Request) -> Response:
        return req.res.text("sync ok")

    @get("/stream")
    async def stream(self, req: Request) -> Response:
        async def gen():
            yield b"a"
            yield "b"

        return req.res.stream(gen(), media_type="text/plain")

    @get("/dev-only")
    @development
    async def dev_only(self, req: Request) -> Response:
        return req.res.text("dev")


@path("/api/users")
class ExtraUserController(Controller):
    """Shares the base path with UserController."""

    @get("/stats")
    async def stats(self, req: Request) -> Response:
        return req.res.json({"count": 1})


@path("/ignored")
@ignore
class IgnoredController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("should not be reachable")


TEMPLATES = {
    "templates/page.html": "<h1>{{ title }}</h1><a href='{{ url_for(\"users.list_users\") }}'>u</a>",
    "templates/error.html": "<p>Error: {{ reason }}</p>",
}


@pytest.fixture
def app(make_app):
    return make_app(
        controllers=[UserController, ExtraUserController, IgnoredController],
        files=TEMPLATES,
    )


async def test_routing_and_hooks(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/api/users/")
        assert res.status_code == 200
        assert res.json() == {"before": True}
        assert res.headers["x-after"] == "1"

        # Without the trailing slash too
        assert (await client.get("/api/users")).status_code == 200

        assert (await client.get("/api/users/stats")).json() == {"count": 1}


async def test_http_methods(app, client_for):
    async with client_for(app) as client:
        assert (await client.put("/api/users/1")).json() == {"method": "PUT", "id": 1}
        assert (await client.patch("/api/users/2")).json() == {
            "method": "PATCH",
            "id": 2,
        }
        res = await client.delete("/api/users/3")
        assert res.status_code == 204
        assert res.content == b""
        assert "content-type" not in res.headers


async def test_response_model_filters_output(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/api/users/5")
        assert res.json() == {"id": 5, "name": "Ana"}


async def test_consumes_validates_body(app, client_for):
    async with client_for(app) as client:
        res = await client.post("/api/users/", json={"name": "Bo", "age": "31"})
        assert res.status_code == 201
        assert res.json() == {"name": "Bo", "age": 31}

        res = await client.post("/api/users/", json={"name": "Bo"})
        assert res.status_code == 422
        body = res.json()
        assert body["message"] == "Validation failed"
        assert body["data"][0]["loc"] == ["age"]
        # The submitted values are not sent back.
        assert "input" not in body["data"][0]

        res = await client.post(
            "/api/users/", content=b"name=x", headers={"content-type": "text/plain"}
        )
        assert res.status_code == 415


async def test_abort_and_http_exceptions_have_default_responses(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/api/users/0")
        assert res.status_code == 404
        assert res.json() == {
            "status": "error",
            "message": "User not found",
            "data": {"id": 0},
        }

        res = await client.get("/api/users/conflict")
        assert res.status_code == 409
        assert res.json()["message"] == "Already exists"


async def test_unhandled_exception_in_debug_mode_propagates(app, client_for):
    async with client_for(app) as client:
        with pytest.raises(RuntimeError, match="unexpected"):
            await client.get("/api/users/crash")


async def test_unhandled_exception_in_production_is_500(make_app, client_for):
    app = make_app(controllers=[UserController], files=TEMPLATES, DEBUG=False)
    async with client_for(app) as client:
        res = await client.get("/api/users/crash")
        assert res.status_code == 500
        assert res.json() == {"status": "error", "message": "Internal server error"}

        res = await client.get("/api/users/not-a-response")
        assert res.status_code == 500

        # development-only endpoints are not registered in production
        assert (await client.get("/api/users/dev-only")).status_code == 404


async def test_development_endpoint_available_in_debug(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/api/users/dev-only")).text == "dev"


async def test_custom_exception_handler_and_inheritance(make_app, client_for):
    @exception_handler
    class Handlers(ExceptionHandler):
        @handles(BaseHttpException)
        async def http_error(self, req: Request, exc: BaseHttpException) -> Response:
            return req.res.json({"handled": exc.message}).status(exc.status_code)

        @handles(RuntimeError)
        def runtime(self, req: Request, exc: RuntimeError) -> Response:
            return req.res.text("runtime handled").status(503)

    app = make_app(
        controllers=[UserController], exception_handlers=[Handlers], files=TEMPLATES
    )
    async with client_for(app) as client:
        # Conflict -> BaseHttpException handler (walks the class hierarchy)
        res = await client.get("/api/users/conflict")
        assert res.status_code == 409
        assert res.json() == {"handled": "Already exists"}

        res = await client.get("/api/users/crash")
        assert res.status_code == 503
        assert res.text == "runtime handled"


async def test_templates_redirects_and_html_abort(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/api/users/page")
        assert res.headers["content-type"] == "text/html; charset=utf-8"
        assert res.text == "<h1>Hi</h1><a href='/api/users/'>u</a>"

        res = await client.get("/api/users/redirect", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/api/users/7"

        res = await client.get("/api/users/html-abort")
        assert res.status_code == 403
        assert res.text == "<p>Error: nope</p>"


async def test_sync_handler_and_streaming(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/api/users/sync")).text == "sync ok"
        res = await client.get("/api/users/stream")
        assert res.text == "ab"
        assert "content-length" not in res.headers


async def test_not_found_and_method_not_allowed(app, client_for):
    async with client_for(app) as client:
        res = await client.get("/nope")
        assert res.status_code == 404
        assert res.json() == {"status": "error", "message": "Endpoint not found"}

        assert (await client.get("/ignored/")).status_code == 404

        for url in ("/api/users/5", "/api/users/stats"):
            res = await client.post(url)
            assert res.status_code == 405
            assert "GET" in res.headers["allow"]


async def test_head_and_automatic_options(app, client_for):
    async with client_for(app) as client:
        res = await client.head("/api/users/5")
        assert res.status_code == 200
        assert res.content == b""
        assert int(res.headers["content-length"]) > 0

        res = await client.request("OPTIONS", "/api/users/5")
        assert res.status_code == 204
        assert set(res.headers["allow"].split(", ")) >= {
            "GET",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        }


async def test_url_for(app):
    assert app.url_for("UserController.get_user", user_id=3) == "/api/users/3"
    assert app.url_for("users.get_user", user_id=3) == "/api/users/3"
    assert app.url_for("static", filename="a.css") == "/static/a.css"
    with pytest.raises(ValueError):
        app.url_for("Nope.nothing")


async def test_url_prefix(make_app, client_for):
    app = make_app(
        controllers=[ExtraUserController],
        files={"static/a.css": "body {}"},
        URL_PREFIX="/v1",
    )
    assert app.url_prefix == "/v1"
    assert app.url_for("ExtraUserController.stats") == "/v1/api/users/stats"
    # Static files keep STATIC_URL.
    assert app.url_for("static", filename="a.css") == "/static/a.css"
    async with client_for(app) as client:
        assert (await client.get("/v1/api/users/stats")).status_code == 200
        assert (await client.get("/api/users/stats")).status_code == 404
        assert (await client.get("/static/a.css")).status_code == 200


async def test_url_prefix_from_the_environment(make_app, client_for, monkeypatch):
    monkeypatch.setenv("PATERA_URL_PREFIX", "/api/v2/")
    app = make_app(controllers=[ExtraUserController])
    assert app.url_prefix == "/api/v2"  # a trailing slash is removed
    async with client_for(app) as client:
        assert (await client.get("/api/v2/api/users/stats")).status_code == 200


@pytest.mark.parametrize(
    ("value", "expected"), [("", ""), ("/", ""), (" /v1/ ", "/v1")]
)
def test_url_prefix_is_normalized(value, expected):
    from patera import BaseConfig

    assert BaseConfig(BASE_PATH=".", URL_PREFIX=value).URL_PREFIX == expected


def test_url_prefix_must_start_with_a_slash():
    from pydantic import ValidationError

    from patera import BaseConfig

    with pytest.raises(ValidationError, match="must start with '/'"):
        BaseConfig(BASE_PATH=".", URL_PREFIX="v1")


def test_the_app_path_decorator_is_gone():
    import patera

    assert not hasattr(patera, "app_path")


async def test_same_controller_in_two_apps(make_app, client_for):
    app1 = make_app(controllers=[ExtraUserController])
    app2 = make_app(controllers=[ExtraUserController])
    for application in (app1, app2):
        async with client_for(application) as client:
            assert (await client.get("/api/users/stats")).status_code == 200


@path("/")
class RootController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.json({"page": "index"})

    @get("/hello")
    async def hello(self, req: Request) -> Response:
        return req.res.json({"page": "hello"})


@pytest.mark.parametrize("prefix", ["", "/v1"])
async def test_joined_route_paths_have_no_double_slashes(make_app, client_for, prefix):
    app = make_app(controllers=[RootController], URL_PREFIX=prefix)
    rules = sorted(
        r.rule
        for r in app.router.url_map.iter_rules()
        if "RootController" in r.endpoint
    )
    assert rules == sorted([f"{prefix}/", f"{prefix}/hello"])
    assert app.url_for("RootController.hello") == f"{prefix}/hello"
    async with client_for(app) as client:
        assert (await client.get(f"{prefix}/hello")).json() == {"page": "hello"}
