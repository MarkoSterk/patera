from __future__ import annotations

import pytest
from pydantic import BaseModel, Field
from typing import Annotated
from patera import Response, MediaType
from patera.controller import produces

from patera import BaseExtension, Request
from patera.ctx import current_request
from patera.injectable import Inject
from patera.joltui import (
    ComponentGroup,
    JoltuiGroupHandler,
    JoltuiRequest,
    PateraJoltui,
    component,
    group,
    joltui_request,
)


class Greeting(BaseExtension):
    value = "hello"


@group("default")
class DefaultGroup(JoltuiGroupHandler):
    greeting: Inject[Greeting]

    @component("home-page")
    def home(self, req: Request):
        assert current_request.request is req
        return req.res.html_body(f"<p>{self.greeting.value}</p>")

    @component("metadata-page")
    async def metadata(self, req: Request):
        assert current_request.request is req
        self.seen = {
            "metadata": joltui_request(req).model_dump(),
            "query": req.query_parameters,
            "cookie": req.cookies.get("session"),
        }
        return req.res.html_body("<p>metadata</p>")

    def private(self, req):
        raise AssertionError("not exposed")


class Interface(PateraJoltui):
    default: ComponentGroup[DefaultGroup]


async def test_protocol_and_request_identity(make_app, client_for):
    app = make_app(extensions=[Interface])
    async with client_for(app) as client:
        response = await client.post(
            "/joltui/components", json={"tagName": " HOME-PAGE "}
        )
        assert response.status_code == 200
        assert response.text == "<p>hello</p>"
        assert "text/html" in response.headers["content-type"]
        response = await client.post(
            "/joltui/components?q=http",
            headers={"cookie": "session=abc"},
            json={
                "tagName": "metadata-page",
                "groupName": "default",
                "routeParameters": {"id": 7},
                "queryParameters": {"q": "frontend"},
                "attributes": {"nested": [1, True]},
            },
        )
        assert response.status_code == 200
        data = app.get_extension(Interface).default.seen
        assert data["metadata"]["route_parameters"] == {"id": 7}
        assert data["metadata"]["query_parameters"] == {"q": "frontend"}
        assert data["metadata"]["attributes"] == {"nested": [1, True]}
        assert data["query"] == {"q": "http"}
        assert data["cookie"] == "abc"
    assert app.get_extension(Interface).default is app.get_extension(DefaultGroup)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"tagName": " "},
        {"tagName": 2},
        {"tagName": "home-page", "attributes": []},
        {"tagName": "home-page", "routeParameters": {"id": []}},
        {"tagName": "home-page", "queryParameters": {"q": 3}},
    ],
)
async def test_invalid_payload(make_app, client_for, payload):
    async with client_for(make_app(extensions=[Interface])) as client:
        res = await client.post("/joltui/components", json=payload)
        assert res.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [{"tagName": "private"}, {"tagName": "home-page", "groupName": "unknown"}],
)
async def test_unknown_component(make_app, client_for, payload):
    async with client_for(make_app(extensions=[Interface])) as client:
        assert (
            await client.post("/joltui/components", json=payload)
        ).status_code == 404


async def test_path_prefix_null_defaults_and_method(make_app, client_for):
    app = make_app(
        extensions=[Interface],
        URL_PREFIX="/api",
        INTERFACE={"COMPONENTS_PATH": "/components"},
    )
    async with client_for(app) as client:
        assert (await client.get("/api/components")).status_code == 405
        assert (await client.post("/api/components", content="{")).status_code == 400
        res = await client.post(
            "/api/components",
            json={
                "tagName": "home-page",
                "groupName": None,
                "attributes": None,
                "routeParameters": None,
                "queryParameters": None,
            },
        )
        assert res.status_code == 200


def test_duplicate_groups(make_app):
    class Duplicate(Interface):
        second: ComponentGroup[DefaultGroup]

    with pytest.raises(ValueError, match="Duplicate JoltUI group"):
        make_app(extensions=[Duplicate])


def test_duplicate_components(make_app):
    @group("duplicate")
    class DuplicateGroup(JoltuiGroupHandler):
        @component("same-tag")
        async def first(self, req):
            pass

        @component("same-tag")
        async def second(self, req):
            pass

    cls = type(
        "DuplicateInterface",
        (PateraJoltui,),
        {"__annotations__": {"group": ComponentGroup[DuplicateGroup]}},
    )
    with pytest.raises(ValueError, match="Duplicate JoltUI component"):
        make_app(extensions=[cls])


async def test_inheritance_and_isolation(make_app, client_for):
    class Child(Interface):
        pass

    one = make_app(extensions=[Child])
    two = make_app(extensions=[Child])
    assert one.get_extension(Child).default is not two.get_extension(Child).default
    async with client_for(two) as client:
        assert (
            await client.post("/joltui/components", json={"tagName": "home-page"})
        ).status_code == 200


async def test_override_removes_component_and_exceptions_propagate(
    make_app, client_for
):
    from patera.exceptions.http_exceptions import BaseHttpException

    @group("user-group")
    class UserGroup(DefaultGroup):
        def home(self, req):
            raise AssertionError("undecorated override must not be exposed")

        @component("denied-page")
        async def denied(self, req):
            raise BaseHttpException("Forbidden", status_code=403)

    cls = type(
        "Users",
        (PateraJoltui,),
        {"__annotations__": {"users": ComponentGroup[UserGroup]}},
    )
    async with client_for(make_app(extensions=[cls])) as client:
        for tag, expected in [
            ("home-page", 404),
            ("denied-page", 403),
            ("metadata-page", 200),
        ]:
            res = await client.post(
                "/joltui/components", json={"groupName": "user-group", "tagName": tag}
            )
            assert res.status_code == expected


async def test_annotation_override_removes_group(make_app, client_for):
    class Removed(Interface):
        default: str

    async with client_for(make_app(extensions=[Removed])) as client:
        assert (
            await client.post("/joltui/components", json={"tagName": "home-page"})
        ).status_code == 404


def test_invalid_group_declarations(make_app):
    class Undecorated(JoltuiGroupHandler):
        pass

    for target, message in [
        (str, "requires a JoltuiGroupHandler"),
        (Undecorated, "needs a @group"),
    ]:
        cls = type(
            "InvalidInterface",
            (PateraJoltui,),
            {"__annotations__": {"invalid": ComponentGroup[target]}},
        )
        with pytest.raises(TypeError, match=message):
            make_app(extensions=[cls])


async def test_controller_and_endpoint_decorators(make_app, client_for):
    from patera import MediaType, HttpStatus, ignore, development
    from patera.controller import (
        after_init,
        before_request,
        after_request,
        produces,
        consumes,
        max_content_length,
        cors,
        no_cors,
        post,
    )
    from patera.auth import login_required, role_required
    from tests.extensions.test_auth import TokenAuth, token

    events = []

    @group("secured")
    @login_required()
    class Secured(JoltuiGroupHandler):
        @after_init
        def ready(self):
            events.append("init")

        @before_request
        async def before(self, req):
            assert current_request.controller is self
            assert req.route_handler.__self__ is self
            events.append("before")

        @after_request
        def after(self, res):
            events.append("after")
            res.set_header("x-hook", "yes")

        @component("admin-page")
        @role_required("admin")
        @produces(MediaType.TEXT_HTML, HttpStatus.CREATED)
        @post("/unused")
        async def admin(self, req):
            events.append("handler")
            return req.res.html_body("<h1>admin</h1>")

        @component("json-page")
        @consumes(MediaType.APPLICATION_JSON)
        async def json_page(self, req, body: JoltuiRequest):
            return req.res.html_body(body.tag_name)

        @component("tiny-page")
        @max_content_length(1)
        async def tiny(self, req):
            raise AssertionError("body limit must run before handler")

        @component("cors-page")
        @cors(allow_origins=["https://allowed.test"])
        async def cors_page(self, req):
            return req.res.html_body("cors")

        @no_cors
        @component("no-cors-page")
        async def no_cors_page(self, req):
            return req.res.html_body("no cors")

        @ignore
        @component("ignored-page")
        async def ignored(self, req):
            raise AssertionError("ignored")

        @component("dev-page")
        @development
        async def dev(self, req):
            return req.res.html_body("dev")

    cls = type(
        "SecuredInterface",
        (PateraJoltui,),
        {"__annotations__": {"secured": ComponentGroup[Secured]}},
    )
    app = make_app(
        extensions=[cls],
        middleware=[TokenAuth],
        DEBUG=False,
        CORS_ENABLED=True,
        CORS_ALLOW_ORIGINS=["https://global.test"],
    )
    assert events == ["init"]
    async with client_for(app) as client:

        async def call(tag, headers=None):
            return await client.post(
                "/joltui/components",
                json={"groupName": "secured", "tagName": tag},
                headers=headers or {},
            )

        assert (await call("admin-page")).status_code == 401
        assert (await call("admin-page", token("bo"))).status_code == 403
        assert events == ["init"]
        res = await call("admin-page", token("ana"))
        assert res.status_code == 201
        assert res.headers["x-hook"] == "yes"
        assert events == ["init", "before", "handler", "after"]
        assert (await call("json-page", token("ana"))).text == "json-page"
        assert (await call("tiny-page", token("ana"))).status_code == 413
        assert (await call("ignored-page", token("ana"))).status_code == 404
        assert (await call("dev-page", token("ana"))).status_code == 404
        res = await call(
            "cors-page", {**token("ana"), "origin": "https://allowed.test"}
        )
        assert res.headers["access-control-allow-origin"] == "https://allowed.test"
        res = await call(
            "no-cors-page", {**token("ana"), "origin": "https://global.test"}
        )
        assert "access-control-allow-origin" not in res.headers
        # OPTIONS has no component envelope and uses the shared URL's policy.
        res = await client.options(
            "/joltui/components",
            headers={
                "origin": "https://global.test",
                "access-control-request-method": "POST",
            },
        )
        assert res.status_code == 204


class UserRoute(BaseModel):
    user_id: int


class UserPageBody(BaseModel):
    route_parameters: UserRoute = Field(alias="routeParameters")


@group("typed")
class TypedGroup(JoltuiGroupHandler):
    @component("typed-page")
    @produces(MediaType.TEXT_HTML)
    async def typed(self, req: Request, body: UserPageBody) -> Response:
        assert (await req.json())["routeParameters"]["user_id"] == "42"
        return req.res.html_body(f"<h1>{body.route_parameters.user_id + 1}</h1>")

    @component("sync-page")
    def sync(self, req: Request, *, body: Annotated[UserPageBody, "body"]):
        return req.res.html_body(f"<h1>{body.route_parameters.user_id}</h1>")

    @component("envelope-page")
    async def envelope(self, req: Request, body: JoltuiRequest):
        return req.res.html_body(f"<h1>{body.tag_name}</h1>")

    @component("string-page")
    async def string(self, req):
        return "<h1>not a response</h1>"

    @component("json-page")
    async def json(self, req):
        return req.res.json({"invalid": True})

    @component("text-page")
    async def text(self, req):
        return req.res.text("<h1>wrong media type</h1>")

    @component("header-page")
    async def header(self, req):
        return req.res.html_body("<h1>wrong header</h1>").set_header(
            "Content-Type", "application/json"
        )


class TypedInterface(PateraJoltui):
    typed: ComponentGroup[TypedGroup]


async def test_automatic_body_model(make_app, client_for):
    async with client_for(make_app(extensions=[TypedInterface])) as client:
        for tag, expected in [
            ("typed-page", "43"),
            ("sync-page", "42"),
            ("envelope-page", "envelope-page"),
        ]:
            res = await client.post(
                "/joltui/components",
                json={
                    "tagName": tag,
                    "groupName": "typed",
                    "routeParameters": {"user_id": "42"},
                },
            )
            assert res.status_code == 200
            assert res.text == f"<h1>{expected}</h1>"
            assert res.headers["content-type"].startswith("text/html")
        for route in [{}, {"user_id": "not-an-integer"}]:
            res = await client.post(
                "/joltui/components",
                json={
                    "tagName": "typed-page",
                    "groupName": "typed",
                    "routeParameters": route,
                },
            )
            assert res.status_code == 422


@pytest.mark.parametrize(
    "tag", ["string-page", "json-page", "text-page", "header-page"]
)
async def test_requires_html_response(make_app, client_for, tag):
    async with client_for(make_app(extensions=[TypedInterface])) as client:
        with pytest.raises(TypeError, match="HTML Response|text/html"):
            await client.post(
                "/joltui/components", json={"tagName": tag, "groupName": "typed"}
            )


def test_envelope_model_names_are_optional():
    body = JoltuiRequest()
    assert body.tag_name is None
    assert body.group_name == "default"
    assert (
        UserPageBody.model_validate(
            {"routeParameters": {"user_id": "42"}}
        ).route_parameters.user_id
        == 42
    )


def test_invalid_body_annotation_fails_at_registration(make_app):
    @group("bad")
    class BadGroup(JoltuiGroupHandler):
        @component("bad-page")
        async def bad(self, req, body: str):
            return req.res.html_body(body)

    cls = type(
        "BadInterface",
        (PateraJoltui,),
        {"__annotations__": {"bad": ComponentGroup[BadGroup]}},
    )
    with pytest.raises(TypeError, match="Pydantic model"):
        make_app(extensions=[cls])


@pytest.mark.parametrize("component_outermost", [True, False])
async def test_consumes_error_preserves_415(make_app, client_for, component_outermost):
    from patera.controller import consumes

    async def page(self, req):
        return req.res.html_body("<p>ok</p>")

    decorators = [component("media-page"), consumes(MediaType.APPLICATION_JSON)]
    if component_outermost:
        decorators.reverse()
    for decorator in decorators:
        page = decorator(page)
    cls = group("default")(type("MediaGroup", (JoltuiGroupHandler,), {"page": page}))
    interface = type(
        "MediaInterface",
        (PateraJoltui,),
        {"__annotations__": {"media": ComponentGroup[cls]}},
    )
    async with client_for(make_app(extensions=[interface])) as client:
        response = await client.post(
            "/joltui/components",
            content='{"tagName":"media-page"}',
            headers={"content-type": "text/plain"},
        )
        assert response.status_code == 415
        assert response.json()["message"] == "Unsupported media type"
        response = await client.post(
            "/joltui/components", json={"tagName": "media-page"}
        )
        assert response.status_code == 200
        assert response.text == "<p>ok</p>"


@pytest.mark.parametrize("status", [200, 503])
async def test_lifecycle_error_preserved_but_success_requires_html(
    make_app, client_for, status
):
    from patera.controller import after_request

    @group("default")
    class HookGroup(JoltuiGroupHandler):
        @component("hook-page")
        async def page(self, req):
            return req.res.html_body("<p>ok</p>")

        @after_request
        def replace(self, response):
            response.json({"error": "unavailable"}).status(status)

    interface = type(
        "HookInterface",
        (PateraJoltui,),
        {"__annotations__": {"hook": ComponentGroup[HookGroup]}},
    )
    async with client_for(make_app(extensions=[interface])) as client:
        if status == 200:
            with pytest.raises(TypeError, match="text/html"):
                await client.post("/joltui/components", json={"tagName": "hook-page"})
        else:
            response = await client.post(
                "/joltui/components", json={"tagName": "hook-page"}
            )
            assert response.status_code == 503
            assert response.json() == {"error": "unavailable"}
