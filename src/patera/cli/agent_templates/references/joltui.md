# patera-joltui

Install `patera-joltui` or `patera[joltui]`; import from `patera.joltui`.
This integrates the TypeScript JoltUI frontend's server-rendered components.
It is distinct from `patera.desktop.ui`'s Python/PyScript components.

```python
from pydantic import BaseModel, Field
from patera import Request, Response
from patera.controller import RequestBody, path
from patera.injectable import Inject
from patera.joltui import (
    ComponentGroup,
    JoltuiController,
    JoltuiGroupHandler,
    PateraJoltui,
    component,
    dispatcher,
    group,
)

class UserRoute(BaseModel):
    user_id: int

class UserPageBody(BaseModel):
    route_parameters: UserRoute = Field(alias="routeParameters")

@group("user-group")
class UserGroupHandler(JoltuiGroupHandler):
    @component("user-page")
    async def user_page(
        self, req: Request, body: RequestBody[UserPageBody]
    ) -> Response:
        return req.res.html_body(f"<h1>User {body.route_parameters.user_id}</h1>")

class JoltuiInterface(PateraJoltui):
    users: ComponentGroup[UserGroupHandler]

@path("/joltui")
class JoltuiComponentsController(JoltuiController):
    joltui: Inject[JoltuiInterface]

    @dispatcher("/components")
    async def components(self, req: Request) -> Response:
        return await self.joltui.dispatch(req)
```

The application owns the component endpoint. Subclass `JoltuiController` and
register one endpoint with `@dispatcher`, which replaces `@post` (do not stack
both): bare `@dispatcher` is a POST route at the controller's path,
`@dispatcher("/components")` one below it; it is left out of OpenAPI unless
`open_api_spec=True`. It returns `await self.<interface>.dispatch(req)` (you may
add headers to the response). The controller's other endpoints are ordinary and
keep their usual decorators. The interface is the controller's single injected
`PateraJoltui` attribute; injecting none or several fails at build, as do a
second `@dispatcher`, another route decorator on it, or a `@dispatcher` outside
a `JoltuiController`. `PateraJoltui` subclasses are injectable services:
`Inject[JoltuiInterface]` creates the app-wide instance. There is no `COMPONENTS_PATH` setting; configuring
it raises an error. Pick any URL; set the frontend's `serverComponentsUrl` to
it, including `URL_PREFIX`. Several interfaces may each have their own controller.

The controller's `@before_request`/`@after_request` hooks run around
`dispatch`. Do not put `@login_required`, `@role_required`, `@transactional`,
`@cors`, or `@no_cors` on the `@dispatcher` endpoint or on the `JoltuiController`:
whether they would guard the request or the component is ambiguous, so the app
refuses to build. Put them on group handlers or component methods; to guard
every component, decorate each group handler. Calling `dispatch` anywhere but
the `@dispatcher` endpoint raises `RuntimeError`.

The request body is the complete RPC envelope:

```json
{"tagName":"user-page","groupName":"user-group","routeParameters":{"user_id":"42"},"queryParameters":{},"attributes":{}}
```

- `ComponentGroup[T]` registers and injects an app-scoped group. Groups support
  normal `Inject[T]` dependencies; keep request-specific state out of instances.
- Always return an HTML `Response`: `req.res.html_body(markup)` or
  `await req.res.html(template_name, ...)`. Plain strings and JSON/text responses
  are rejected. Escape client input in raw markup; use templates as appropriate.
- The optional third parameter must be annotated `RequestBody[Model]`. The
  extension validates the **full body**, not just `attributes`, and injects the
  model by parameter name. No `@consumes` is needed. Use aliases for camelCase
  fields and nested models for typed route/query/attribute data. Normal Pydantic
  coercion and extra-field rules apply. Models need not declare routing names;
  Pydantic's default ignores those extra fields. An `extra="forbid"` model must
  explicitly account for the envelope fields it accepts.
- `RequestBody[JoltuiRequest]` can also be the third parameter. Its Python names are
  `tag_name`, `group_name`, `route_parameters`, `query_parameters`, `attributes`.
  Names are optional when constructing this model; dispatch still requires a
  nonempty `tagName`. Omitted/null groups select `default`; omitted/null maps
  become `{}`. Tags are lowercased; group names are case-sensitive.
- Without a body parameter, `joltui_request(req)` retrieves validated metadata.
  The original Patera `Request` remains intact: its route/query parameters are
  the HTTP URL's, not the frontend's. `await req.json()` returns the original body.
- Malformed envelopes return 400, unknown components return 404, and handler
  model validation returns 422. Validation happens after authentication and
  before-request hooks, before the handler executes.

Groups use normal controller lifecycle hooks and endpoint decorators. Auth
decorators on groups/methods require the application's authentication middleware.
The dispatch middleware resolves the bound component before CORS, database,
auth, and application middleware; `req.route_handler` and
`current_request.controller` identify that component and group. `@consumes`
remains supported for the original envelope. `@produces` operates on a Response.
Successful responses require HTML; responses with status 400 or higher retain
their normal media type, including decorator-generated 415 errors. Response
caching requires `@cache(..., methods=("POST",))` opt-in for this read-only RPC
transport; default keys include the full body digest. Add a callable key for
header-dependent variants.
Inherited methods work; an undecorated override removes component exposure.
`@ignore` and `@development` affect group/component registration.

All components of an interface share its POST URL. HTTP route decorators do not create extra
component URLs; WebSockets and per-component OpenAPI routes are not provided.
OPTIONS has no envelope, so preflights use the global CORS policy. Configure it
for the frontend; component CORS settings apply to actual POSTs. The initial
application body limit protects parsing before a component's smaller
`@max_content_length` limit can be checked.

Test through `PateraTestClient` with lifespan enabled. Exercise the actual JSON
envelope, HTML media type, model coercion/422 failures, unknown registrations,
and group/endpoint authentication when applicable.
