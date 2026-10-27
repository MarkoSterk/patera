# Controllers and routing

```python
from patera import HttpStatus, Request, Response, MediaType
from patera.controller import Controller, path, get, post, consumes
from pydantic import BaseModel

class NoteInput(BaseModel):
    title: str

@path("/notes")
class NotesController(Controller):
    @get("/<int:note_id>")
    async def read(self, req: Request, note_id: int) -> Response:
        return req.res.json({"id": note_id})

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    async def create(self, req: Request, data: NoteInput) -> Response:
        return req.res.json(data.model_dump()).status(HttpStatus.CREATED)
```

Place in `controllers/notes_controller.py` or the corresponding API discovery
folder/pattern. Routing uses Werkzeug-style `<name>` and `<int:name>` converters,
not `{name}` syntax. Query parameters are read explicitly from
`req.query_parameters`; they do not become handler arguments automatically.
Validate them with `req.validate(QueryModel, req.query_parameters)`.

Use `@before_request`, `@after_request`, and `@after_init` from
`patera.controller` for controller hooks. Inspect installed signatures when adding
hooks. Do not override framework construction to perform injection yourself.
Controller instances are shared across concurrent requests.

Endpoint names default to `Class.method`; `@path` and route aliases affect URL
generation. Use `app.url_for`/template `url_for` instead of assembling prefixed
URLs. Keep controller and CLI alias spaces distinct. Duplicate route definitions
are errors. `STRICT_SLASHES` controls slash handling; GET also supports HEAD and
the router handles OPTIONS. Test method errors and slash behavior when changing
routes.

Sources: tutorial chapter 3; architecture chapter 7.
