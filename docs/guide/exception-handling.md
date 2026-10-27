# Exception handling

Exception handlers are classes with methods mapped to exception types:

```python
from patera import HttpStatus, Request, Response
from patera.exceptions import (
    BaseHttpException,
    ExceptionHandler,
    RequestValidationError,
    exception_handler,
    handles,
)


class EntityNotFound(BaseHttpException):
    def __init__(self, message: str):
        super().__init__(message, HttpStatus.NOT_FOUND)


@exception_handler
class ApiExceptionHandler(ExceptionHandler):

    @handles(RequestValidationError)
    async def validation_error(self, req: Request, exc: RequestValidationError) -> Response:
        return req.res.json({"message": "Invalid data", "details": exc.errors}).status(HttpStatus.UNPROCESSABLE_ENTITY)

    @handles(BaseHttpException)          # also handles subclasses, e.g. EntityNotFound
    async def http_error(self, req: Request, exc: BaseHttpException) -> Response:
        return req.res.json({"message": exc.message, "data": exc.data}).status(exc.status_code)
```

Put the class in an `exceptions` folder (file name containing `handler`) or register it with
`app.register_exception_handler(...)`.

- `@handles` accepts several exception classes and can be stacked.
- A handler registered for a base class also handles its subclasses; lookup follows the
  exception's MRO and the **most specific** handler wins.
- Exceptions raised in [middleware](middleware.md) are handled by the exception handlers too.

A handler can return any response, for example RFC 9457 problem details:

```python
from patera import HttpStatus

@handles(MissingNote)
async def missing(self, req: Request, exc: MissingNote) -> Response:
    return req.res.problem("Note not found", str(exc), HttpStatus.NOT_FOUND)
```

## Default responses

Without a matching handler:

| Exception | Response |
| --- | --- |
| `BaseHttpException` and subclasses (`abort()`, authentication errors, ...) | JSON `{"status", "message", "data"}` with the exception's status code |
| `RequestValidationError` (from `@consumes` or `req.validate()`, a `BaseHttpException`) | `422` with `{"status": "error", "message": "Validation failed", "data": [...]}` |
| anything else, including a `pydantic.ValidationError` from your own code or data | `DEBUG=True`: the exception propagates (traceback in the server log). `DEBUG=False`: `500` `{"status": "error", "message": "Internal server error"}` and the error is logged |

Other built-in statuses: a malformed body is `400`, a media type mismatch `415`, an oversized
body `413`.

Override `default_exception_response(req, exc)` on the application class to change this fallback.

## Quick aborts

```python
from patera import HttpStatus, abort, html_abort

abort("User not found", HttpStatus.NOT_FOUND, data={"id": user_id})   # JSON error response
html_abort("errors/404.html", HttpStatus.NOT_FOUND, {"id": user_id})  # renders the template
```

## Special cases

- `HtmlAborterException` and `StaticPageNotFound` have special dispatch: register their exact
  classes to replace their handling. A generic `BaseHttpException` handler does not capture them.
- Routing failures (`404`, `405`) occur outside ordinary controller and middleware handling.
- The framework resets unfinished responses before replacing them with an error. Once sending has
  started (for example a [stream](responses.md#streaming)), failures propagate without sending a
  second response; disconnects cannot be answered either.
- `Response[Model]` conversion does not apply to 4xx/5xx bodies. Build and validate an error
  schema explicitly if you need one.
