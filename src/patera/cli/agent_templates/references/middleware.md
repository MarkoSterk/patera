# Middleware, context, and CORS

```python
from patera import Request, Response
from patera.middleware import MiddlewareBase, middleware
from patera.ctx import current_request

@middleware(order=10)
class TraceMiddleware(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        current_request.set("trace_source", "http")
        res = await self.next(req)
        res.set_header("X-Trace-Source", "http")
        return res
```

Use a matching path such as `middleware/trace_middleware.py`. Supply a distinct
positive order for application middleware. Lower values enter first and exit
last. Built-in CORS/database/auth middleware use -101/-100/-99 respectively.
Register before the middleware chain is built, normally at first ASGI lifespan.
An extension registers middleware classes in `init()`.

Use locals or `current_request.set/get` for per-request data. The proxy also
exposes request/app and session lookup; `has_request_context()` checks availability.
Do not keep request-specific values on the middleware singleton.

Routing precedes the HTTP middleware chain. Static files bypass it, and sockets
have a separate path. Do not rely on middleware to protect static assets or to
observe every response. Use `app.add_request_observer` for complete HTTP records.

For credentialed CORS, declare specific frontend origins, methods and headers in
`CORS_ALLOW_ORIGINS`, `CORS_ALLOW_METHODS`, and `CORS_ALLOW_HEADERS`; enable
`CORS_ENABLED` and, when required, `CORS_ALLOW_CREDENTIALS`. Controller decorators
`cors`/`no_cors` provide overrides. CORS is not authentication or CSRF protection.

Sources: tutorial chapter 5; architecture chapter 9.
