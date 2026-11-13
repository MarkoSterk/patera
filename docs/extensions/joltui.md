# JoltUI

`patera-joltui` serves server components for JoltUI, the TypeScript SPA framework by Marko
Šterk, with typed group registration.

```sh
uv add "patera[joltui]"
```

## Setup

```python
from html import escape

from patera import Request, Response
from patera.controller import path
from patera.injectable import Inject
from patera.joltui import (
    ComponentGroup, JoltuiController, JoltuiGroupHandler, PateraJoltui,
    component, dispatcher, group, joltui_request,
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


@path("/joltui")
class JoltuiComponentsController(JoltuiController):
    joltui: Inject[JoltuiInterface]

    @dispatcher("/components")
    async def components(self, req: Request) -> Response:
        return await self.joltui.dispatch(req)
```

`JoltuiInterface` is an injectable service. The application owns the endpoint: the `POST`
route that `@dispatcher` registers in a `JoltuiController` subclass receives the component
requests, calls `dispatch(req)` on the controller's injected interface and returns its response.
Register the controller as usual; injecting the interface creates its app-wide instance, and the
controller registers the small dispatch middleware the interface needs.

Set JoltUI's `serverComponentsUrl` to the endpoint's URL (here `/joltui/components`, including
Patera's `URL_PREFIX`, if configured). Any URL works, and several interfaces may each have their
own controller.

!!! note "Upgrading from the auto-registered controller"

    Earlier versions registered `POST /joltui/components` themselves and read
    `JoltuiConfig.COMPONENTS_PATH`. Both were removed: add the controller above with the URL you
    used, and delete the `COMPONENTS_PATH` setting (configuring it now raises an error).

## The component controller

- `@dispatcher` registers the controller's single component endpoint as a `POST` route and
  replaces `@post`: bare `@dispatcher` serves the controller's own path, and
  `@dispatcher("/components")` a path below it. The route is left out of the OpenAPI document
  unless you pass `open_api_spec=True` (and optionally `tags=[...]`). Every other endpoint of the
  controller (`GET`, `POST`, `PUT` and so on) is ordinary and takes its usual decorators,
  `@login_required()` included.
- The controller's interface is its single injected `PateraJoltui` attribute (it may be
  inherited from a base controller). A `JoltuiController` that injects no interface, or several,
  fails when the application builds, as do a second `@dispatcher` endpoint, another route
  decorator (`@post`, `@get`, ...) on the `@dispatcher` endpoint, and a `@dispatcher` endpoint
  outside a `JoltuiController`.
- The controller's hooks (`@before_request`, `@after_request`) run around `dispatch`, and the
  endpoint may modify the returned response, for example to add headers.
- Authentication, transactions and CORS belong to groups and components.
  `@login_required()`, `@role_required()`, `@transactional`, `@cors` and `@no_cors` are not
  supported on the `@dispatcher` endpoint or on the `JoltuiController` itself: it would be
  ambiguous whether they guard the component request or the component, and the middleware that
  reads them sees the selected component. The application refuses to build. To guard every
  component, put the decorator on each group handler.
- A `JoltuiController` without a `@dispatcher` endpoint, and an interface without one, log a
  warning.
- `dispatch` raises `RuntimeError` when called anywhere but the `@dispatcher` endpoint of a
  `JoltuiController` that injects that interface.

## The request envelope

JoltUI sends a JSON `POST` containing `tagName`, `groupName`, `routeParameters`,
`queryParameters` and `attributes`.

- Omitted or null groups default to `default`; omitted or null parameter mappings default to
  empty dictionaries.
- Tags are trimmed and lowercased; group names remain case-sensitive.
- Malformed requests return `400`; unknown groups or components return `404`.

Handlers receive the original Patera `Request`, with cookies, sessions, headers, request context
and response helpers. `joltui_request(req)` provides the validated frontend metadata as
`tag_name`, `group_name`, `route_parameters`, `query_parameters` and `attributes`. HTTP URL
parameters stay unchanged, and the original JSON is available through `await req.json()`.

## Responses

Always return a Patera `Response` with content type `text/html`, for example
`req.res.html_body(markup)` or `await req.res.html("user.html", ...)`. Plain strings and non-HTML
successful responses are rejected. Sync handlers are supported.

Error responses (status 400 or higher), including the JSON `415` of `@consumes` and
lifecycle-generated errors, keep their normal media type and status. Handler exceptions follow
Patera's normal [exception pipeline](../guide/exception-handling.md), including `401` and `403`.

## Validated bodies

Handlers may declare an optional third argument annotated `RequestBody[Model]` (from
`patera.controller`) with any Pydantic model. The extension validates the full JSON body into that model; `@consumes` is not required. Validation failures
return `422` before the handler runs (after authentication and `@before_request` hooks).

```python
from pydantic import BaseModel, Field

from patera import Response
from patera.controller import RequestBody


class UserRoute(BaseModel):
    user_id: int


class UserPageBody(BaseModel):
    route_parameters: UserRoute = Field(alias="routeParameters")
    # tagName and groupName need not be declared in a custom model.


@group("user-group")
class UserGroupHandler(JoltuiGroupHandler):
    @component("user-page")
    async def user_page(
        self, req: Request, body: RequestBody[UserPageBody]
    ) -> Response:
        return req.res.html_body(f"<h1>User {body.route_parameters.user_id}</h1>")
```

For the body
`{"tagName": "user-page", "groupName": "user-group", "routeParameters": {"user_id": "42"}}`,
`body.route_parameters.user_id` is the integer `42`. Use `RequestBody[JoltuiRequest]` as the third argument
when its standard fields suffice (`tag_name` defaults to `None`, `group_name` to `"default"`).

## Groups are controllers

Group handlers are Patera [controllers](../guide/controllers.md). Use the normal decorators,
including group and component `@login_required()` / `@role_required()`, `@after_init`,
`@before_request`, `@after_request`, `@consumes`, `@produces`, `@cors`, `@no_cors`,
`@max_content_length`, `@ignore` and `@development`:

```python
from patera import MediaType
from patera.auth import login_required, role_required
from patera.controller import after_request, produces


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

- Groups are application-scoped singletons and support `Inject[T]`. Do not store per-request data
  on them.
- Inherited component methods are exposed; overriding a method without `@component` removes its
  registration. Duplicate group names or component tags fail at initialization.
- Only decorated methods in explicitly declared groups are callable. Interface annotations may be
  inherited, overridden, or removed with a non-`ComponentGroup` annotation.
- Component selection runs in a middleware (order `-102`) before CORS, database,
  authentication and application middleware. Middleware sees the selected component as
  `req.route_handler` and its group as `current_request.controller`; `req.endpoint` stays the
  component endpoint the application calls.

## Caching, CORS and limits

- [Response caching](caching.md) defaults to `GET`/`HEAD`. To cache a read-only component, opt in
  with `@cache("PUBLIC_CACHE", methods=("POST",))`; the default key includes a digest of the
  complete body.
- All components of an interface share its `POST` URL. They are not separate OpenAPI routes, and
  no WebSocket transport is provided.
- `OPTIONS` preflights have no component body, so they use the global CORS policy; configure it to permit the frontend. Component CORS overrides apply to actual `POST`
  responses.
- The application's body limit protects envelope parsing; component `@max_content_length` limits
  are enforced after selection.

!!! warning

    Frontend metadata is client input, not an authorization source. Escape values inserted into
    raw HTML, or use templates.
