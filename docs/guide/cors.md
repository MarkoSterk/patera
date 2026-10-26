# CORS

CORS is enabled by default and configured with the `CORS_*` options:

| Option | Default | Description |
| --- | --- | --- |
| `CORS_ENABLED` | `True` | Global CORS handling. |
| `CORS_ALLOW_ORIGINS` | `["*"]` | Allowed origins. |
| `CORS_ALLOW_METHODS` | `["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]` | Allowed methods. |
| `CORS_ALLOW_HEADERS` | `["Authorization", "Content-Type"]` | Allowed request headers. |
| `CORS_EXPOSE_HEADERS` | `[]` | Response headers exposed to the browser. |
| `CORS_ALLOW_CREDENTIALS` | `False` | Allow cookies and `Authorization` on cross-origin requests (the request origin is echoed instead of `*`). |
| `CORS_MAX_AGE` | `None` | Preflight cache time in seconds. |

```sh
PATERA_CORS_ALLOW_ORIGINS='["https://app.example.com"]'
PATERA_CORS_ALLOW_CREDENTIALS=true
```

## Behaviour

- The middleware answers preflight requests (`OPTIONS` with `Access-Control-Request-Method`) and
  adds CORS headers to all responses of allowed origins, including error responses.
- Requests from origins that are not allowed are processed normally but without CORS headers, so
  the browser blocks cross-origin reads while same-origin requests keep working. Preflights from
  such origins get `403`.
- Every response of a route with CORS enabled carries `Vary: Origin`, so shared caches keep the
  variants apart.

!!! warning "Credentials"

    Turn on `CORS_ALLOW_CREDENTIALS` only together with an explicit `CORS_ALLOW_ORIGINS` list,
    and declare specific methods and headers. CORS is not authentication or CSRF protection.

## Per endpoint

```python
from patera.controller import cors, no_cors

@get("/partner-data")
@cors(allow_origins=["https://partner.example.com"], allow_credentials=False, max_age=600)
async def partner_data(self, req: Request) -> Response: ...

@get("/internal")
@no_cors
async def internal(self, req: Request) -> Response: ...
```
