# patera-joltui

Install `patera-joltui` or `patera[joltui]`; import from `patera.joltui`.
This integrates the TypeScript JolUI frontend's server-rendered components.
It is distinct from `patera.desktop.ui`'s Python/PyScript components.

```python
from pydantic import BaseModel, Field
from patera import Request, Response
from patera.joltui import ComponentGroup, JoltuiGroupHandler, PateraJoltui, component, group

class UserRoute(BaseModel):
    user_id: int

class UserPageBody(BaseModel):
    route_parameters: UserRoute = Field(alias="routeParameters")

@group("user-group")
class UserGroupHandler(JoltuiGroupHandler):
    @component("user-page")
    async def user_page(self, req: Request, body: UserPageBody) -> Response:
        return req.res.html_body(f"<h1>User {body.route_parameters.user_id}</h1>")

class JoltuiInterface(PateraJoltui):
    users: ComponentGroup[UserGroupHandler]
```

Register `JoltuiInterface` in `app_extensions` or use `Inject[JoltuiInterface]`.
The extension owns the POST controller: do not add another dispatch route.
`JoltuiConfig.COMPONENTS_PATH` defaults to `/joltui/components`. Configure this
subclass with `JOLTUI_INTERFACE = {"COMPONENTS_PATH": "/ui/components"}`.
Set the frontend's `serverComponentsUrl` to the endpoint, including `URL_PREFIX`.

The request body is the complete RPC envelope:

```json
{"tagName":"user-page","groupName":"user-group","routeParameters":{"user_id":"42"},"queryParameters":{},"attributes":{}}
```

- `ComponentGroup[T]` registers and injects an app-scoped group. Groups support
  normal `Inject[T]` dependencies; keep request-specific state out of instances.
- Always return an HTML `Response`: `req.res.html_body(markup)` or
  `await req.res.html(template_name, ...)`. Plain strings and JSON/text responses
  are rejected. Escape client input in raw markup; use templates as appropriate.
- The optional third parameter must be annotated with a Pydantic model. The
  extension validates the **full body**, not just `attributes`, and injects the
  model by parameter name. No `@consumes` is needed. Use aliases for camelCase
  fields and nested models for typed route/query/attribute data. Normal Pydantic
  coercion and extra-field rules apply. Models need not declare routing names;
  Pydantic's default ignores those extra fields. An `extra="forbid"` model must
  explicitly account for the envelope fields it accepts.
- `JoltuiRequest` can also be the third parameter. Its Python names are
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
Inherited methods work; an undecorated override removes component exposure.
`@ignore` and `@development` affect group/component registration.

All components share one POST URL. HTTP route decorators do not create extra
component URLs; WebSockets and per-component OpenAPI routes are not provided.
OPTIONS has no envelope, so preflights use the global CORS policy. Configure it
for the frontend; component CORS settings apply to actual POSTs. The initial
application body limit protects parsing before a component's smaller
`@max_content_length` limit can be checked.

Test through `PateraTestClient` with lifespan enabled. Exercise the actual JSON
envelope, HTML media type, model coercion/422 failures, unknown registrations,
and group/endpoint authentication when applicable.
