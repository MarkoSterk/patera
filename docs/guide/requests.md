# Requests

Every endpoint receives a `Request` as its first argument after `self`.

| Member | Description |
| --- | --- |
| `method`, `path`, `query_string`, `headers` (lower-case keys) | request line and headers |
| `query_parameters` | dict; repeated keys become lists |
| `query_list(name)` | all values of a query parameter as a list |
| `route_parameters` | parsed route parameters |
| `await body()`, `await json()` | raw body / parsed JSON (`None` if empty; malformed JSON is `400`) |
| `await form()`, `await files()`, `await form_and_files()` | url-encoded and multipart data |
| `await form_list(name)` | all values of a form field as a list |
| `validate(Model, data)` | validates client data the handler reads itself |
| `await get_data(location)` | `"json"`, `"form"`, `"files"`, `"form_and_files"` or `"query"` |
| `user`, `roles`, `set_user()`, `set_roles()` | authenticated user (see [Authentication](../extensions/authentication.md)) |
| `context` | request-scoped storage |
| `app`, `res` / `response` | the application and the response being built |

## Bodies

Parsing is lazy. Await `req.body()`, `req.json()`, `req.form()`, `req.files()` or
`req.form_and_files()` as needed; do not consume the ASGI `receive` channel yourself.

```python
from patera import HttpStatus

@post("/notes")
async def create(self, req: Request) -> Response:
    data = await req.json()
    return req.res.json({"title": data["title"]}).status(HttpStatus.CREATED)
```

- An empty body gives `None`; malformed JSON is answered with `400`.
- A broken multipart body is answered with `400`.
- A body larger than `MAX_CONTENT_LENGTH` (default 10 MB, override per endpoint with
  `@max_content_length`) is answered with `413`.
- A client that disconnects mid-body raises `ClientDisconnected`: the handler stops and no
  response is sent.

For JSON and forms that map to a model, prefer `@consumes` with a Pydantic parameter; see
[Controllers](controllers.md#request-bodies-and-validation).

## Uploaded files

Files are `UploadedFile` objects (importable from `patera`):

| Member | Description |
| --- | --- |
| `filename`, `content_type`, `size` | metadata sent by the client |
| `read()`, `seek()` | read like a file |
| `save(path)` | write to disk |
| `stream` | the underlying stream |

```python
@post("/avatars")
async def upload(self, req: Request) -> Response:
    files = await req.files()
    avatar = files["avatar"]
    avatar.save(os.path.join(self.upload_dir, f"{uuid4()}.png"))
    return req.res.no_content()
```

!!! warning

    Pick safe storage names rather than trusting the upload's `filename`, and never store private
    uploads under the public static directory.

## Validation

`req.validate(Model, data)` validates client data the handler reads itself, such as query
parameters or route values. Invalid data raises `RequestValidationError`, answered with `422`:

```python
class Paging(BaseModel):
    page: int = 1
    per_page: int = 20


@get("/")
async def index(self, req: Request) -> Response:
    paging = req.validate(Paging, req.query_parameters)
    ...
```

A plain `pydantic.ValidationError` raised elsewhere in your code is an application failure, not
a client error. Use `req.validate` for user input.

## Request context

`req.context` is request-scoped storage:

```python
req.context.set("trace_id", trace_id)
trace_id = req.context.get("trace_id")
```

The current request is also available anywhere during request handling through
`patera.ctx.current_request`. It exposes `set`/`get`, the request and the application;
`has_request_context()` checks whether a request is active.

```python
from patera.ctx import current_request

current_request.set("trace_source", "http")
```

Use the context (or local variables) for per-request data; never store it on controllers,
services or middleware, which are shared singletons.
