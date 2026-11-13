# Middleware

Middleware wraps the request handling chain:

```python
# app/middleware/timing_mw.py
import time

from patera import Request, Response
from patera.middleware import MiddlewareBase, middleware


@middleware(order=10)
class TimingMiddleware(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        start = time.perf_counter()
        res = await self.next(req)          # or return a response directly (short-circuit)
        res.set_header("x-process-time-ms", str(int((time.perf_counter() - start) * 1000)))
        return res
```

## Headers, cookies and query parameters

After `req`, a middleware method may declare `Headers[Model]`, `Cookies[Model]` and
`QueryParams[Model]` parameters, as [endpoints](controllers.md#headers-and-cookies) do. They are
validated on every request (`422` when invalid) and passed in:

```python
class TenantHeaders(BaseModel):
    x_tenant: str                       # X-Tenant
    x_request_id: UUID | None = None


@middleware(order=20)
class TenantMiddleware(MiddlewareBase):
    async def middleware(self, req: Request, tenant: Headers[TenantHeaders]) -> Response:
        req.context.set("tenant", tenant.x_tenant)
        return await self.next(req)
```

- A required field applies to **every** request that passes through the middleware, including
  the Swagger page. Use defaults for values that are optional anywhere.
- Nothing else is injected: any other parameter after `req`, including a bare model, fails at
  startup. `RequestBody` and `Files` are endpoint-only, because the body's media type belongs
  to the endpoint's `@consumes`.
- The fields are documented on every [OpenAPI](openapi.md) operation. Set the class attribute
  `open_api_spec = False` for middleware that acts only on some paths.
- `middleware(self, req)` keeps working unchanged.

## Registration

Middleware is discovered in `middleware` folders (file names containing `middleware` or `mw`) or
registered explicitly before the first request:

```python
app.register_middleware(TimingMiddleware, order=10)
```

An [extension](custom-extensions.md) registers its middleware classes in `init()`.

## Order

Lower order numbers run first (outermost): they enter first and exit last. Built-in middleware
uses negative orders:

| Middleware | Order |
| --- | --- |
| Observability ([telemetry](../extensions/telemetry.md), request records) | `-200` and below |
| [JoltUI](../extensions/joltui.md) component dispatch | `-102` |
| CORS | `-101` |
| SQL session manager ([database](../extensions/database.md)) | `-100` |
| [Authentication](../extensions/authentication.md) | `-99` |

Give application middleware distinct positive orders. If an order is taken, the next free number
is used and a warning is logged. `patera.middleware.ORDER_TIERS` lists the reserved tiers.

## Configuration

Middleware can declare a configuration model just like [services](dependency-injection.md#service-configuration):
`MiddlewareBase[App, MyConfig]`, available as `self.configs` and read from the config field named
after the class (`TimingMiddleware` → `TIMING_MIDDLEWARE`). Middleware supports dependency
injection with `Inject[...]`.

## Which requests middleware sees

Every HTTP request passes through the middleware chain, including requests no route matched and
[static files](static-files.md). By default a middleware runs only for requests that matched a
route and are not static files. Two class attributes opt in to the others:

```python
@middleware(order=1)
class RequestMetrics(MiddlewareBase):
    run_on_unmatched = True   # 404, 405 and trailing-slash redirects
    run_on_static = True      # the static files controller

    async def middleware(self, req: Request) -> Response:
        res = await self.next(req)
        self.app.logger.info(f"{req.method} {req.path} {res.status_code}")
        return res
```

- **Unmatched requests.** `req.route_matched` is `False`, and `req.routing_outcome` says why:
  its `kind` is `"not_found"`, `"method_not_allowed"`, `"protocol_mismatch"` or `"redirect"`,
  with the `status` that is answered. Reading `req.route_handler` raises `RuntimeError`.
- **Their response is already sent** when `await self.next(req)` returns: `req.response_started`
  is `True`, and the returned response only carries the status code, so changing it has no
  effect. To add headers, [wrap the send channel](#wrapping-the-send-channel). A middleware can
  still answer an unmatched request itself by returning a response without calling `next`.
- **Static files.** `req.static_resource` is `True`. Middleware that does not opt in, including
  [authentication](../extensions/authentication.md), never runs for them: everything in the
  static folder is public.
- A required `Headers[...]`, `Cookies[...]` or `QueryParams[...]` field applies to every request
  the middleware runs for: with `run_on_unmatched`, an unknown path without the header is answered
  with 422 instead of 404.

## Wrapping the send channel

`req.wrap_send(wrapper)` installs `wrapper(send)` as the request's ASGI send channel. Every message
of the response passes through it, including error responses and the responses to unmatched
requests:

```python
async def middleware(self, req: Request) -> Response:
    def add_server_timing(send):
        async def timed_send(message):
            if message["type"] == "http.response.start":
                headers = [*message["headers"], (b"server-timing", b"app")]
                message = {**message, "headers": headers}
            await send(message)

        return timed_send

    req.wrap_send(add_server_timing)
    return await self.next(req)
```

CORS adds its headers this way. A wrapper also sees when the body ends (the last
`http.response.body` message has no `more_body`), which is when a streamed response is complete.

## What middleware does not see

- [WebSockets](websockets.md) have a separate path; HTTP middleware is not applied to them.
- Middleware is a singleton: keep per-request values in locals or the
  [request context](requests.md#request-context).

A [request observer](logging.md#request-observers) is the simplest way to record every completed
HTTP response: a plain callback, called after the response has been sent.

Exceptions raised in middleware are handled by the [exception handlers](exception-handling.md).
