from __future__ import annotations

import pytest
from pydantic import BaseModel, Field
from typing import Annotated
from patera import Response, MediaType
from patera.controller import Controller, RequestBody, path, post, produces

from patera import BaseExtension, Request
from patera.ctx import current_request
from patera.injectable import Inject
from patera.joltui import (
    ComponentGroup,
    JoltuiController,
    JoltuiGroupHandler,
    JoltuiRequest,
    PateraJoltui,
    component,
    dispatcher,
    group,
    joltui_request,
)


def components_controller(interface, url="/joltui/components"):
    """The developer-owned component endpoint, as documented."""

    @path(url)
    class Components(JoltuiController):
        Target = interface
        joltui: Inject[Target]

        @dispatcher
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    Components.__name__ = f"{interface.__name__}Components"
    return Components


def joltui_app(make_app, interface, url="/joltui/components", **config):
    return make_app(controllers=[components_controller(interface, url)], **config)


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
    app = joltui_app(make_app, Interface)
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
    async with client_for(joltui_app(make_app, Interface)) as client:
        res = await client.post("/joltui/components", json=payload)
        assert res.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [{"tagName": "private"}, {"tagName": "home-page", "groupName": "unknown"}],
)
async def test_unknown_component(make_app, client_for, payload):
    async with client_for(joltui_app(make_app, Interface)) as client:
        assert (
            await client.post("/joltui/components", json=payload)
        ).status_code == 404


async def test_path_prefix_null_defaults_and_method(make_app, client_for):
    app = joltui_app(make_app, Interface, "/components", URL_PREFIX="/api")
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
        joltui_app(make_app, Duplicate)


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
        joltui_app(make_app, cls)


async def test_inheritance_and_isolation(make_app, client_for):
    class Child(Interface):
        pass

    one = joltui_app(make_app, Child)
    two = joltui_app(make_app, Child)
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
    async with client_for(joltui_app(make_app, cls)) as client:
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

    async with client_for(joltui_app(make_app, Removed)) as client:
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
            joltui_app(make_app, cls)


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
        async def json_page(self, req, body: RequestBody[JoltuiRequest]):
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
    app = joltui_app(
        make_app,
        cls,
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
    async def typed(self, req: Request, body: RequestBody[UserPageBody]) -> Response:
        assert (await req.json())["routeParameters"]["user_id"] == "42"
        return req.res.html_body(f"<h1>{body.route_parameters.user_id + 1}</h1>")

    @component("sync-page")
    def sync(self, req: Request, *, body: Annotated[RequestBody[UserPageBody], "body"]):
        return req.res.html_body(f"<h1>{body.route_parameters.user_id}</h1>")

    @component("envelope-page")
    async def envelope(self, req: Request, body: RequestBody[JoltuiRequest]):
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
    async with client_for(joltui_app(make_app, TypedInterface)) as client:
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
    async with client_for(joltui_app(make_app, TypedInterface)) as client:
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
        joltui_app(make_app, cls)


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
    async with client_for(joltui_app(make_app, interface)) as client:
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
    async with client_for(joltui_app(make_app, interface)) as client:
        if status == 200:
            with pytest.raises(TypeError, match="text/html"):
                await client.post("/joltui/components", json={"tagName": "hook-page"})
        else:
            response = await client.post(
                "/joltui/components", json={"tagName": "hook-page"}
            )
            assert response.status_code == 503
            assert response.json() == {"error": "unavailable"}


def test_bare_model_body_fails_at_registration(make_app):
    @group("bare")
    class BareGroup(JoltuiGroupHandler):
        @component("bare-page")
        async def bare(self, req, body: UserPageBody):
            return req.res.html_body("bare")

    cls = type(
        "BareInterface",
        (PateraJoltui,),
        {"__annotations__": {"bare": ComponentGroup[BareGroup]}},
    )
    with pytest.raises(TypeError, match=r"RequestBody\[Model\]"):
        joltui_app(make_app, cls)


# The application owns the component endpoint.


async def test_endpoint_body_and_controller_hooks_wrap_dispatch(make_app, client_for):
    from patera.controller import after_request, before_request

    events: list[str] = []

    @path("/ui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @before_request
        def before(self, req: Request):
            events.append("before")

        @after_request
        def after(self, res: Response):
            events.append(f"after {res.status_code}")

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            events.append("endpoint")
            res = await self.joltui.dispatch(req)
            return res.set_header("X-Rendered-By", "pages")

    app = make_app(controllers=[Pages])
    async with client_for(app) as client:
        res = await client.post("/ui/components", json={"tagName": "home-page"})
    assert res.status_code == 200
    assert res.text == "<p>hello</p>"
    assert res.headers["x-rendered-by"] == "pages"
    assert events == ["before", "endpoint", "after 200"]
    assert app.get_extension(Interface) is app.get_extension(Interface)


@group("default")
class OtherGroup(JoltuiGroupHandler):
    @component("home-page")
    def home(self, req: Request):
        return req.res.html_body("<p>other</p>")


class OtherInterface(PateraJoltui):
    default: ComponentGroup[OtherGroup]


async def test_two_interfaces_on_two_controllers(make_app, client_for):
    app = make_app(
        controllers=[
            components_controller(Interface, "/one"),
            components_controller(OtherInterface, "/two"),
        ]
    )
    async with client_for(app) as client:
        one = await client.post("/one", json={"tagName": "home-page"})
        two = await client.post("/two", json={"tagName": "home-page"})
    assert (one.text, two.text) == ("<p>hello</p>", "<p>other</p>")


async def test_other_endpoints_are_ordinary(make_app, client_for):
    from patera.controller import get, no_cors, put

    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

        @get("/components")
        @no_cors
        async def page(self, req: Request) -> Response:
            return req.res.html_body("<main></main>")

        @post("/notes")
        async def note(self, req: Request) -> Response:
            # Not a component request: any JSON body, any response type.
            return req.res.json({"saved": (await req.json())["text"]})

        @put("/notes")
        async def replace(self, req: Request) -> Response:
            return req.res.json({"replaced": True})

        @post("/misused")
        async def misused(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    async with client_for(make_app(controllers=[Pages])) as client:
        res = await client.get("/joltui/components")
        assert (res.status_code, res.text) == (200, "<main></main>")
        res = await client.post("/joltui/notes", json={"text": "hi"})
        assert (res.status_code, res.json()) == (200, {"saved": "hi"})
        assert (await client.put("/joltui/notes")).json() == {"replaced": True}
        component = await client.post(
            "/joltui/components", json={"tagName": "home-page"}
        )
        assert component.text == "<p>hello</p>"
        with pytest.raises(RuntimeError, match="the @dispatcher endpoint"):
            await client.post("/joltui/misused", json={"tagName": "home-page"})


async def test_ordinary_endpoints_keep_their_decorators(make_app, client_for):
    from patera.controller import get
    from tests.extensions.test_auth import TokenAuth, token

    from patera.auth import login_required

    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

        @get("/private")
        @login_required()
        async def private(self, req: Request) -> Response:
            return req.res.html_body("<p>private</p>")

    app = make_app(controllers=[Pages], middleware=[TokenAuth])
    async with client_for(app) as client:
        assert (await client.get("/joltui/private")).status_code == 401
        res = await client.get("/joltui/private", headers=token("cy"))
        assert (res.status_code, res.text) == (200, "<p>private</p>")
        res = await client.post("/joltui/components", json={"tagName": "home-page"})
        assert res.status_code == 200


@pytest.mark.parametrize("decorator", ["login_required", "cors", "no_cors"])
def test_dispatcher_decorators_that_would_be_ambiguous_are_rejected(
    make_app, decorator
):
    from patera.auth import login_required
    from patera.controller import cors, no_cors

    mark = {
        "login_required": login_required(),
        "cors": cors(allow_origins=["https://x.test"]),
        "no_cors": no_cors,
    }[decorator]

    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher("/components")
        @mark
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    app = make_app(controllers=[Pages])
    with pytest.raises(TypeError, match="on the @dispatcher endpoint is not supported"):
        app.build()


@pytest.mark.parametrize("decorator", ["login_required", "cors", "no_cors"])
def test_controller_decorators_are_rejected(make_app, decorator):
    from patera.auth import login_required
    from patera.controller import cors, no_cors

    mark = {
        "login_required": login_required(),
        "cors": cors(allow_origins=["https://x.test"]),
        "no_cors": no_cors,
    }[decorator]

    @mark
    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    app = make_app(controllers=[Pages])
    with pytest.raises(TypeError, match="on a JoltuiController is not supported"):
        app.build()


async def test_bare_dispatcher_serves_the_controller_path(make_app, client_for):
    @path("/joltui/components")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    app = make_app(controllers=[Pages], URL_PREFIX="/api")
    async with client_for(app) as client:
        res = await client.post("/api/joltui/components", json={"tagName": "home-page"})
        assert res.text == "<p>hello</p>"
        assert (await client.get("/api/joltui/components")).status_code == 405


def test_dispatcher_is_left_out_of_openapi_by_default(make_app):
    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    @path("/documented")
    class Documented(JoltuiController):
        joltui: Inject[OtherInterface]

        @dispatcher("/components", open_api_spec=True, tags=["joltui"])
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    paths = make_app(controllers=[Pages, Documented]).json_spec["paths"]
    assert "/joltui/components" not in paths
    assert "joltui" in paths["/documented/components"]["post"]["tags"]


def test_dispatcher_replaces_the_route_decorator_below_it():
    with pytest.raises(TypeError, match="registers its own POST route"):

        class Pages(JoltuiController):
            @dispatcher("/components")
            @post("/components")
            async def render(self, req: Request) -> Response:
                return req.res.html_body("")


@pytest.mark.parametrize("route", ["post", "get"])
def test_dispatcher_rejects_a_route_decorator_above_it(make_app, route):
    from patera.controller import get

    decorator = {"post": post, "get": get}[route]

    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @decorator("/other")
        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    app = make_app(controllers=[Pages])
    with pytest.raises(TypeError, match="registers its own POST route"):
        app.build()


def test_dispatcher_takes_a_path_string():
    with pytest.raises(TypeError, match="optional URL path string"):
        dispatcher(3)  # type: ignore[call-overload]


def test_controller_has_a_single_dispatcher(make_app):
    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher("/one")
        async def one(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

        @dispatcher("/two")
        async def two(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    app = make_app(controllers=[Pages])
    with pytest.raises(TypeError, match="single @dispatcher endpoint"):
        app.build()


def test_dispatcher_requires_joltui_controller(make_app):
    @path("/joltui")
    class Plain(Controller):
        joltui: Inject[Interface]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    app = make_app(controllers=[Plain])
    with pytest.raises(TypeError, match="belong to a JoltuiController subclass"):
        app.build()


def test_controller_without_interface_is_rejected(make_app):
    @path("/joltui")
    class Pages(JoltuiController):
        greeting: Inject[Greeting]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return req.res.html_body("")

    app = make_app(controllers=[Pages])
    with pytest.raises(TypeError, match=r"exactly one PateraJoltui .*found: none"):
        app.build()


def test_controller_with_several_interfaces_is_rejected(make_app):
    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]
        other: Inject[OtherInterface]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    app = make_app(controllers=[Pages])
    with pytest.raises(TypeError, match=r"exactly one .*found: joltui, other"):
        app.build()


async def test_controller_without_dispatcher_is_ordinary(make_app, client_for):
    @path("/joltui")
    class Pages(JoltuiController):
        joltui: Inject[Interface]

        @post("/components")
        async def render(self, req: Request) -> Response:
            return req.res.html_body("<p>plain</p>")

    async with client_for(make_app(controllers=[Pages])) as client:
        res = await client.post("/joltui/components", json={"tagName": "home-page"})
    assert res.text == "<p>plain</p>"


async def test_interface_and_dispatcher_are_inherited(make_app, client_for):
    class Base(JoltuiController):
        joltui: Inject[Interface]

        @dispatcher("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    @path("/joltui")
    class Pages(Base):
        pass

    async with client_for(make_app(controllers=[Pages])) as client:
        res = await client.post("/joltui/components", json={"tagName": "home-page"})
    assert res.text == "<p>hello</p>"


async def test_dispatch_requires_dispatcher_endpoint(make_app, client_for):
    @path("/joltui")
    class Plain(Controller):
        joltui: Inject[Interface]

        @post("/components")
        async def render(self, req: Request) -> Response:
            return await self.joltui.dispatch(req)

    async with client_for(make_app(controllers=[Plain])) as client:
        with pytest.raises(
            RuntimeError,
            match="@dispatcher endpoint of a JoltuiController that injects Interface",
        ):
            await client.post("/joltui/components", json={"tagName": "home-page"})


def test_components_path_configuration_was_removed(make_app):
    with pytest.raises(Exception, match="COMPONENTS_PATH was removed"):
        joltui_app(make_app, Interface, INTERFACE={"COMPONENTS_PATH": "/c"})


async def test_interface_without_endpoint_serves_nothing(make_app, client_for):
    async with client_for(make_app(extensions=[Interface])) as client:
        res = await client.post("/joltui/components", json={"tagName": "home-page"})
    assert res.status_code == 404
