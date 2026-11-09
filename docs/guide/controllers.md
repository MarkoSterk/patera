# Controllers and routing

A controller is a class that groups endpoints under a base path:

```python
from typing import TYPE_CHECKING

from pydantic import BaseModel

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import (
    Controller, QueryParams, RequestBody, after_request, before_request, consumes, delete, get,
    path, post, produces,
)

if TYPE_CHECKING:
    from app import App


class UserIn(BaseModel):
    name: str


class UserQuery(BaseModel):
    page: int = 1
    tags: list[str] = []
    email: str


class UserOut(BaseModel):
    id: int
    name: str


@path("/api/v1/users", tags=["Users"], alias="users")
class UserApi(Controller["App"]):

    @get("/")
    async def list_users(
        self, req: Request, query: QueryParams[UserQuery]
    ) -> Response[list[UserOut]]:
        return req.res.json([{"id": 1, "name": "Ana"}])

    @get("/<int:user_id>")
    async def get_user(self, req: Request, user_id: int) -> Response[UserOut]:
        return req.res.json({"id": user_id, "name": "Ana", "password_hash": "..."})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    async def create_user(self, req: Request, user: RequestBody[UserIn]) -> Response[UserOut]:
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

Query parameters are declared with a model; see below.

## Request bodies and validation

A Pydantic model parameter declares where its data comes from with one of these annotations from
`patera.controller`:

| Annotation | Built from |
| --- | --- |
| `RequestBody[Model]` | the request body, read as the `@consumes` media type |
| `QueryParams[Model]` | the query string |
| `Files[...]` | the files of a multipart body ([Uploaded files](#uploaded-files)) |
| `Headers[Model]`, `Cookies[Model]` | request headers and cookies ([Headers and cookies](#headers-and-cookies)) |

All are `Annotated` aliases: editors and type checkers see a plain `Model`.

```python
@post("/")
@consumes(MediaType.APPLICATION_JSON)
@produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
async def create_user(
    self, req: Request, data: RequestBody[UserIn], query: QueryParams[UserQuery]
) -> Response[UserOut]:
    ...
```

`@consumes(MediaType)` requires the request to have this content type (otherwise `415`) and reads
the body: JSON, url-encoded form or multipart form (including `UploadedFile` fields). The
`RequestBody` parameter is built from it.

- A handler has at most one `RequestBody`; it may have several `QueryParams` models, each built
  from the same query string.
- A JSON body may be any type Pydantic validates, such as `RequestBody[list[UserIn]]`; an
  invalid item is reported as `["body", 1, "name"]`. A form body is one set of fields, so form
  and multipart endpoints need a model.
- Query values are strings that Pydantic converts (`"2"` to `2`). A list field accepts a single
  value or a repeated key: `?tags=a` and `?tags=a&tags=b`. The same applies to form fields
  (checkboxes, multi-selects).
- Invalid data raises `RequestValidationError`: `422` with the validation errors, without the
  submitted values, unless you [handle](exception-handling.md) it yourself. Each error's `loc`
  starts with `"body"`, `"query"`, `"files"`, `"header"` or `"cookie"`.
- Mistakes fail at startup, when the controller is registered: a model parameter without one of
  these annotations, a `RequestBody` without `@consumes`, two `RequestBody` parameters, or
  `@consumes` on a GET endpoint.
- Raw values stay available: `req.query_parameters`, `await req.json()`, `await req.form()`.
  Validate data the handler assembles itself with `req.validate(Model, data)`
  (see [Requests](requests.md#validation)).

### Uploaded files

A multipart `RequestBody[Model]` receives text fields and files together: declare files as
`UploadedFile` or `list[UploadedFile]` fields of the model. To keep files out of the model, take
them with `Files[...]` parameters, bound to the file field of the same name:

```python
@post("/profile")
@consumes(MediaType.MULTIPART_FORM_DATA)
async def update_profile(
    self,
    req: Request,
    data: RequestBody[ProfileForm],
    avatar: Files[UploadedFile],
    attachments: Files[list[UploadedFile]],
) -> Response:
    ...
```

| Annotation | Receives |
| --- | --- |
| `Files[UploadedFile]` | exactly one file; missing or repeated is `422` (`["files", "avatar"]`) |
| `Files[UploadedFile \| None]` (or `= None`) | one file, or `None` |
| `Files[list[UploadedFile]]` | every file of that field; `[]` when none was sent |
| `Files[Model]` | a model whose fields are files, named by field name or alias |
| `Files[dict[str, list[UploadedFile]]]` | every file of the request, by field name |

`Files[Model]` validates files like any model, so a `field_validator` can check a file's name,
type or size; its errors are `422` at `["files", "<field>", ...]`. A field alias binds a file
field whose name is not a Python identifier:

```python
class ProfileFiles(BaseModel):
    picture: UploadedFile = Field(alias="profile-picture")
    documents: list[UploadedFile] = []

    @field_validator("picture")
    @classmethod
    def must_be_png(cls, value: UploadedFile) -> UploadedFile:
        if not value.filename.lower().endswith(".png"):
            raise ValueError("The profile picture must be a PNG file")
        return value
```

Every field of a `Files` model must be a file field, and each file field is bound by one
parameter only.

With `Files` parameters the `RequestBody` model gets the text fields only, so it must not
declare file fields or fields named like a `Files` parameter; both fail at startup, as does
`Files` without `@consumes(MediaType.MULTIPART_FORM_DATA)`. A handler may also take only `Files`
parameters. OpenAPI documents the form fields and the files as one `multipart/form-data` object
with binary file properties.

### Headers and cookies

`Headers[Model]` and `Cookies[Model]` build a model from request headers and cookies, like
`QueryParams[Model]` does from the query string. The parameter's name does not matter; the
model's fields name the headers or cookies:

```python
class ClientHeaders(BaseModel):
    user_agent: str                                     # User-Agent
    x_request_id: UUID | None = None                    # X-Request-Id
    client_ip: str = Field(alias="X-Forwarded-For")
    accept_language: list[str] = []                     # every Accept-Language line


class SessionCookies(BaseModel):
    session_id: str
    token: str | None = Field(default=None, alias="__Host-token")


@get("/")
async def index(
    self,
    req: Request,
    headers: Headers[ClientHeaders],
    cookies: Cookies[SessionCookies],
) -> Response:
    ...
```

| | Headers | Cookies |
| --- | --- | --- |
| Name without an alias | the field name with `-` for `_`: `x_request_id` reads `X-Request-Id` | the field name |
| Letter case | ignored, as in HTTP | must match exactly |
| Other names | `Field(alias="X-Forwarded-For")` | `Field(alias="__Host-token")` |
| `list[...]` field | every value of a header sent several times, one per header line | |

- Only the declared headers and cookies are passed to the model, so `extra="forbid"` is safe.
  A missing name leaves the field's default.
- Errors name what the client sent: `["header", "x-request-id"]`, `["cookie", "session_id"]`.
- An alias must be a plain string, and two fields may not read the same header or cookie; both
  fail at startup.
- OpenAPI lists each field as an `in: header` or `in: cookie` parameter. `Accept`,
  `Content-Type` and `Authorization` are left out, because OpenAPI ignores them as header
  parameters.
- WebSocket handlers do not take these parameters; read `req.headers` and `req.cookies` there.

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
