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
| CORS | `-101` |
| SQL session manager ([database](../extensions/database.md)) | `-100` |
| [Authentication](../extensions/authentication.md) | `-99` |

Give application middleware distinct positive orders. If an order is taken, the next free number
is used and a warning is logged.

## Configuration

Middleware can declare a configuration model just like [services](dependency-injection.md#service-configuration):
`MiddlewareBase[App, MyConfig]`, available as `self.configs` and read from the config field named
after the class (`TimingMiddleware` → `TIMING_MIDDLEWARE`). Middleware supports dependency
injection with `Inject[...]`.

## What middleware does not see

- Routing precedes the middleware chain.
- [Static files](static-files.md) bypass middleware, so middleware cannot protect static assets.
- [WebSockets](websockets.md) have a separate path; HTTP middleware is not applied to them.
- Middleware is a singleton: keep per-request values in locals or the
  [request context](requests.md#request-context).

To observe every completed HTTP response, including static files and routing failures, use a
[request observer](logging.md#request-observers).

Exceptions raised in middleware are handled by the [exception handlers](exception-handling.md).
