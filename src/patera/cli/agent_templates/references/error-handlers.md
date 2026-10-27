# Exception handlers

```python
from patera import HttpStatus, Request, Response
from patera.exceptions import ExceptionHandler, exception_handler, handles

class MissingNote(Exception):
    pass

@exception_handler
class ApplicationErrors(ExceptionHandler):
    @handles(MissingNote)
    async def missing(self, req: Request, exc: MissingNote) -> Response:
        return req.res.problem("Note not found", str(exc), HttpStatus.NOT_FOUND)
```

Place in `exceptions/app_exception_handler.py`, or register the class with
`app.register_exception_handler`. `@handles` accepts multiple classes and can be
stacked. Lookup follows exception MRO to the most specific registered handler.

`abort(message, status_code)` and `html_abort(template, status_code)` from `patera`
raise HTTP exceptions. Default JSON uses `status`, `message`, and optional `data`.
Request validation becomes 422; malformed bodies 400; media mismatch 415; oversized
bodies 413. A plain Pydantic `ValidationError` is not universally a client error.
Use `req.validate` for user input instead of catching all validation errors.

`HtmlAborterException` and `StaticPageNotFound` have special dispatch: register
their exact classes to replace their handling. A generic `BaseHttpException`
handler does not capture those cases. Routing failures occur outside ordinary
controller/middleware handling.

The framework resets unfinished responses before replacement errors. Once sending
has started, failures propagate without sending a second response; disconnects
also cannot be answered. Renderer failures have an outer boundary. Unhandled
production failures return a neutral 500 and log details; debug failures propagate.
Construct an error schema explicitly if it needs validation, since success-body
`Response[Model]` conversion does not apply to 4xx/5xx bodies.

Sources: tutorial chapters 3 and 5; architecture chapter 10.
