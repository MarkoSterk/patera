# OpenAPI

With `OPEN_API=True` (default), the specification is served at `/openapi/specs.json` and a
Swagger UI at `/openapi/docs`.

The specification is generated from your controllers:

| Source | Becomes |
| --- | --- |
| routes and path parameters | paths |
| `@consumes` + Pydantic parameters | request bodies |
| `@produces` and `Response[Model]` annotations | responses |
| `@open_api_docs(Descriptor(...))` | additional (error) responses |
| `@path(tags=...)`, endpoint `tags=...` | tags |
| docstrings | descriptions |

```python
from patera.controller import Descriptor, open_api_docs


@get("/<int:user_id>")
@open_api_docs(Descriptor(404, "User not found", MediaType.APPLICATION_JSON, ErrorBody))
async def get_user(self, req: Request, user_id: int) -> Response[UserOut]:
    """Returns one user."""
    ...
```

Exclude a controller or endpoint with `open_api_spec=False`.

The document's server is relative (`URL_PREFIX`, or `/`), so "Try it out" calls the origin that
served the page, behind a proxy too.

## Settings

| Option | Default | Description |
| --- | --- | --- |
| `OPEN_API` | `True` | Serve the specification and Swagger UI. |
| `OPEN_API_URL` | `"/openapi"` | Base URL of the documentation. |
| `OPEN_API_DESCRIPTION` | `"Simple API"` | Description in the specification. |
| `APP_NAME` / `VERSION` | | Title and version of the specification. |

The specification is also available in code as `app.json_spec`.

!!! tip

    Use `@consumes`, `@produces` and `@open_api_docs` from `patera.controller` for incoming HTTP
    endpoints, not the identically named decorators of the [API interface](../extensions/apiinterface.md).
    Verify the generated schema after changing annotations.
