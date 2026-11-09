# Controllers and routing

For every HTTP endpoint, explicitly declare its response media type and success
status with `@produces`. For endpoints accepting a request body, declare the
accepted media type with `@consumes` and annotate the body model parameter as
`RequestBody[Model]`. Annotate a query-string model as `QueryParams[Model]`.
Document expected errors using
`@open_api_docs` and `Descriptor`, including validation errors and applicable
authentication, authorization, missing-resource, or conflict responses.
Use `HttpStatus` members for every status.

Put the route decorator outermost, as shown below. Keep request and response
annotations and decorator metadata consistent with actual behavior. A bodyless
GET needs no `@consumes`. Supply error descriptors for responses the endpoint
can actually return. Verify the generated OpenAPI after changing the contract.

```python
from typing import TYPE_CHECKING

from patera import HttpStatus, Request, Response, MediaType
from patera.controller import (
    Controller, Descriptor, path, get, post, consumes, produces, open_api_docs,
    QueryParams, RequestBody,
)
from pydantic import BaseModel

if TYPE_CHECKING:
    from app import App


class NoteInput(BaseModel):
    title: str

class NoteQuery(BaseModel):
    page: int = 1

@path("/notes")
class NotesController(Controller["App"]):
    @get("/<int:note_id>")
    @produces(MediaType.APPLICATION_JSON, HttpStatus.OK)
    async def read(self, req: Request, note_id: int) -> Response:
        return req.res.json({"id": note_id})

    @get("/")
    @produces(MediaType.APPLICATION_JSON, HttpStatus.OK)
    @open_api_docs(
        Descriptor(HttpStatus.UNPROCESSABLE_ENTITY, "Invalid query parameters"),
    )
    async def index(self, req: Request, query: QueryParams[NoteQuery]) -> Response:
        return req.res.json({"page": query.page, "notes": []})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @open_api_docs(
        Descriptor(HttpStatus.BAD_REQUEST, "Malformed JSON body"),
        Descriptor(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "Expected a JSON body"),
        Descriptor(HttpStatus.UNPROCESSABLE_ENTITY, "Invalid note input"),
    )
    async def create(self, req: Request, data: RequestBody[NoteInput]) -> Response:
        return req.res.json(data.model_dump())
```

Place in `controllers/notes_controller.py` or the corresponding API discovery
folder/pattern. Routing uses Werkzeug-style `<name>` and `<int:name>` converters,
not `{name}` syntax. Route values are passed to parameters of the same name.
A Pydantic parameter must declare its source: `RequestBody[Model]` (requires
`@consumes`), `QueryParams[Model]`, `Files[...]` (multipart only), `Headers[Model]`
or `Cookies[Model]`; an unmarked model parameter fails at registration. JSON
bodies may use other types, such as `RequestBody[list[Model]]`; form bodies need a
model. Invalid values are answered with 422 and each error's `loc` starts with
`"body"`, `"query"`, `"files"`, `"header"` or `"cookie"`. A list field accepts a repeated query key.

Use `@before_request`, `@after_request`, and `@after_init` from
`patera.controller` for controller hooks. A `@before_request` hook may declare
`Headers[Model]`, `Cookies[Model]` and `QueryParams[Model]` after `req`; other
parameters fail at registration. Inspect installed signatures when adding
hooks. Do not override framework construction to perform injection yourself.
Controller instances are shared across concurrent requests.

Endpoint names default to `Class.method`; `@path` and route aliases affect URL
generation. Use `app.url_for`/template `url_for` instead of assembling prefixed
URLs. Keep controller and CLI alias spaces distinct. Duplicate route definitions
are errors. `STRICT_SLASHES` controls slash handling; GET also supports HEAD and
the router handles OPTIONS. Test method errors and slash behavior when changing
routes.

Sources: tutorial chapter 3; architecture chapter 7.
