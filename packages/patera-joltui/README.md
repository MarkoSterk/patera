# patera-joltui

Install `patera-joltui` (or `patera[joltui]`) and import from `patera.joltui`.

```python
from html import escape
from patera import Request
from patera.injectable import Inject
from patera.joltui import (
    ComponentGroup, JoltuiGroupHandler, PateraJoltui,
    component, group, joltui_request,
)

@group("default")
class DefaultGroupHandler(JoltuiGroupHandler):
    @component("home-page")
    async def home_page(self, req: Request):
        return req.res.html_body("<h1>Welcome</h1>")

@group("user-group")
class UserGroupHandler(JoltuiGroupHandler):
    @component("user-page")
    async def user_page(self, req: Request):
        data = joltui_request(req)
        user_id = escape(str(data.route_parameters["user_id"]))
        return req.res.html_body(f"<h1>User {user_id}</h1>")

class JoltuiInterface(PateraJoltui):
    default_group: ComponentGroup[DefaultGroupHandler]
    user_group: ComponentGroup[UserGroupHandler]
```

Register `JoltuiInterface` in your application's `app_extensions`, or inject it
with `joltui: Inject[JoltuiInterface]`. Set JolUI's `serverComponentsUrl` to
`/joltui/components` (including Patera's `URL_PREFIX`, if configured).
Override the endpoint with application configuration:
`JOLTUI_INTERFACE = {"COMPONENTS_PATH": "/components"}`.
The extension registers its own controller automatically; no application
controller or manual dispatch route is needed. `JoltuiConfig.COMPONENTS_PATH`
defaults to `/joltui/components`.

JolUI sends a JSON POST containing `tagName`, `groupName`, `routeParameters`,
`queryParameters`, and `attributes`. Omitted/null groups default to `default`;
omitted/null parameter mappings default to empty dictionaries. Tags are
trimmed and lowercased, while group names remain case-sensitive.

Handlers receive the original Patera `Request`, retaining cookies, sessions,
headers, request context, and response helpers. `joltui_request(req)` provides
validated frontend metadata as `tag_name`, `group_name`, `route_parameters`,
`query_parameters`, and `attributes`. HTTP URL parameters stay unchanged;
frontend route parameters are accessed through this metadata. The original
JSON is also available through `await req.json()`.

Always return a Patera `Response` with content type `text/html` (for example,
`req.res.html_body(markup)` or `await req.res.html("user.html", ...)`).
Plain strings and non-HTML responses are rejected. Sync handlers are supported too.
Malformed requests return 400; unknown groups/components return 404. Handler
exceptions follow Patera's normal exception pipeline, including 401/403.

Groups are app-scoped and support `Inject[T]` dependencies. Do not store
per-request data on group instances. Inherited component methods are exposed;
overriding a method without `@component` removes its registration. Duplicate
group names or component tags fail at initialization. Only decorated methods
in explicitly declared groups are callable. Interface annotations may be
inherited, overridden, or removed with a non-ComponentGroup annotation.

Group handlers are Patera controllers. Use the normal controller and endpoint
decorators, including group/endpoint `@login_required()` and `@role_required()`,
`@after_init`, `@before_request`, `@after_request`, `@consumes`, `@produces`,
`@cors`, `@no_cors`, `@max_content_length`, `@ignore`, and `@development`.
Authentication decorators require the application's usual authentication
middleware. For example:

```python
from patera.auth import login_required, role_required
from patera.controller import after_request, produces
from patera import MediaType

@group("user-group")
@login_required()
class UserGroupHandler(JoltuiGroupHandler):
    @after_request
    def prevent_caching(self, res):
        res.set_header("Cache-Control", "no-store")

    @component("user-page")
    @role_required("admin")
    @produces(MediaType.TEXT_HTML)
    async def user_page(self, req: Request):
        return req.res.html_body("<h1>Users</h1>")
```

Component selection runs before CORS, database, authentication, and application
middleware. They see the selected bound component as `req.route_handler` and
its group as `current_request.controller`. Normal controller hooks run once;
after-request hooks receive the handler's HTML `Response`.
Decorators such as `@produces` that operate on a response expect handlers to
return a `Response`, just as on ordinary endpoints. `@consumes` validates the
original JSON envelope, not just its `attributes` field.

All components share one HTTP POST URL: `@path`/HTTP method decorators do not
create additional component URLs, and WebSocket transport is not provided by
this endpoint. OpenAPI metadata can be attached, but individual RPC components
are not separate OpenAPI routes. OPTIONS preflights have no component body,
so they use the shared endpoint's global CORS policy; configure it to permit
the frontend. Component CORS overrides apply to actual POST responses.

The application's body limit protects JSON envelope parsing. Component
`@max_content_length` limits are additionally enforced after selection and
cannot bypass that initial envelope limit. Frontend metadata is client input,
not an authorization source. Escape values inserted into raw HTML, or use
your application's templates.


Handlers may declare an optional third argument annotated with any Pydantic
model. The extension validates the full JSON body into that model automatically;
`@consumes` is not required. Model validation failures return 422 before the
handler runs. Authentication and controller before-request hooks run first.

```python
from pydantic import BaseModel, Field
from patera import Response

class UserRoute(BaseModel):
    user_id: int

class UserPageBody(BaseModel):
    route_parameters: UserRoute = Field(alias="routeParameters")
    # tagName and groupName need not be declared in a custom model.
    # Pydantic's default extra="ignore" ignores undeclared envelope fields.

@group("user-group")
class UserGroupHandler(JoltuiGroupHandler):
    @component("user-page")
    async def user_page(self, req: Request, body: UserPageBody) -> Response:
        return req.res.html_body(f"<h1>User {body.route_parameters.user_id}</h1>")
```

For example, the request body is:

```json
{"tagName": "user-page", "groupName": "user-group", "routeParameters": {"user_id": "42"}}
```

`body.route_parameters.user_id` is validated and converted to the integer 42.
The original `Request` and its JSON body remain available. Use `JoltuiRequest`
as the third argument if its standard fields suffice, or define your own model
with nested models and aliases as above. `JoltuiRequest.tag_name` defaults to
`None` and `group_name` to `"default"`, so neither field is required when
constructing the model. The actual RPC envelope still requires `tagName` to
select the handler; `groupName` may be omitted to select the default group.
Custom models receive the original body and follow their own Pydantic defaults,
coercion, extra-field policy, and validators.
