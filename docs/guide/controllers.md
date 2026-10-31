# Controllers and routing

A controller is a class that groups endpoints under a base path:

```python
from typing import TYPE_CHECKING

from pydantic import BaseModel

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import (
    Controller, after_request, before_request, consumes, delete, get, path, post, produces,
)

if TYPE_CHECKING:
    from app import App


class UserIn(BaseModel):
    name: str
    email: str


class UserOut(BaseModel):
    id: int
    name: str


@path("/api/v1/users", tags=["Users"], alias="users")
class UserApi(Controller["App"]):

    @get("/")
    async def list_users(self, req: Request) -> Response[list[UserOut]]:
        return req.res.json([{"id": 1, "name": "Ana"}])

    @get("/<int:user_id>")
    async def get_user(self, req: Request, user_id: int) -> Response[UserOut]:
        return req.res.json({"id": user_id, "name": "Ana", "password_hash": "..."})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    async def create_user(self, req: Request, user: UserIn) -> Response[UserOut]:
        return req.res.json({"id": 2, "name": user.name})

    @delete("/<int:user_id>")
    async def delete_user(self, req: Request, user_id: int) -> Response:
        return req.res.no_content()

    @before_request
    async def before(self, req: Request) -> None:
        ...  # runs before every endpoint of this controller

    @after_request
    async def after(self, res: Response) -> None:
        res.set_header("x-controller", "users")
```

Controller instances are shared across concurrent requests: keep request data in local variables
or the [request context](requests.md#request-context), not on `self`.

## The controller decorator

`@path(url, open_api_spec=True, tags=None, alias=None)` sets the base path of the controller.

- `alias` is an alternative name for `url_for`: `url_for("users.get_user", user_id=1)`. The
  class name always works too: `url_for("UserApi.get_user", user_id=1)`.
- Several controllers may share a base path.
- `tags` group the endpoints in [OpenAPI](openapi.md); `open_api_spec=False` hides the
  controller from the specification.
- `URL_PREFIX` from the [configuration](configuration.md) is prepended to every controller route.

## Endpoints

`@get`, `@post`, `@put`, `@patch`, `@delete(url, open_api_spec=True, tags=None)` declare
endpoints.

- The first argument after `self` is always the `Request`; route parameters are passed as
  keyword arguments.
- Handlers may be `async` or plain functions; plain functions run in a thread pool.
- Duplicate route definitions are errors (`DuplicateRouteError`).

### Route parameters

Route parameters use
[Werkzeug converters](https://werkzeug.palletsprojects.com/en/stable/routing/#built-in-converters),
not `{name}` syntax:

| Pattern | Matches |
| --- | --- |
| `<name>` | a string without slashes |
| `<int:id>` | an integer |
| `<float:x>` | a float |
| `<uuid:key>` | a UUID |
| `<path:rest>` | a string including slashes |

Query parameters do **not** become handler arguments. Read them from `req.query_parameters` and
validate them with `req.validate(Model, data)` (see [Requests](requests.md#validation)).

## Request bodies and validation

`@consumes(MediaType)` requires the request to have this content type (otherwise `415`).
Parameters annotated with a Pydantic model are validated from the JSON body, url-encoded form or
multipart form (including `UploadedFile` fields).

- For forms, a single value of a field the model declares as a list (checkboxes, multi-selects)
  arrives as a one-item list.
- Invalid data raises `RequestValidationError`: `422` with the validation errors, without the
  submitted values, unless you [handle](exception-handling.md) it yourself.

## Responses and response models

`@produces(MediaType, status_code=HttpStatus.OK)` sets the default media type and status code. An
explicitly set content type or status wins (also `.status(HttpStatus.OK)`). Both are documented
in OpenAPI.

Annotating the return type as `-> Response[Model]` validates and serializes the body through
`Model`, which filters out undeclared fields (`password_hash` above):

- generic annotations such as `list[Model]` or `dict[str, Model]` filter every item,
- dictionaries, model instances and objects with matching attributes (ORM rows) are accepted,
- only 2xx bodies are shaped this way; error bodies keep their own fields,
- the annotation also documents the response in OpenAPI.

## Controller hooks

| Decorator | Runs |
| --- | --- |
| `@before_request` | before every endpoint of the controller; receives the request |
| `@after_request` | after every endpoint; receives the response |
| `@after_init` | once, after the controller is created and its dependencies are injected |

## Other endpoint decorators

| Decorator | Purpose |
| --- | --- |
| `@open_api_docs(Descriptor(status, description, media_type, body))` | document additional (error) responses |
| `@cors(...)` / `@no_cors` | per-endpoint [CORS](cors.md) settings |
| `@max_content_length(limit)` | override `MAX_CONTENT_LENGTH` for one endpoint (`None` for no limit) |
| `@development` | the endpoint (or controller) only exists in debug mode |
| `@ignore` | never registered |
| `@socket(url)` | a [WebSocket](websockets.md) endpoint |

## Routing behaviour

- With `STRICT_SLASHES=False` (default), `/users` and `/users/` reach the same endpoint.
- Unknown paths return `404` (JSON). A known path with the wrong method returns `405` with an
  `Allow` header.
- `HEAD` requests are answered by the matching `GET` endpoint, without a body.
- `OPTIONS` requests to routes without an explicit handler return `204` with an `Allow` header
  (CORS preflight requests are answered by the [CORS middleware](cors.md)).

## Building URLs

Use `url_for` instead of assembling prefixed URLs by hand. It is available on the application
and in [templates](templates.md):

```python
self.app.url_for("UserApi.get_user", user_id=1)   # class name
self.app.url_for("users.get_user", user_id=1)     # alias
self.app.url_for("static", filename="site.css")   # static files
```

Endpoint names default to `Class.method`. Keep controller and CLI alias spaces distinct.
