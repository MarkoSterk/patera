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

After `req`, `middleware()` and controller `@before_request` hooks may declare
`Headers[Model]`, `Cookies[Model]` and `QueryParams[Model]` parameters (import
from `patera.controller`); they are validated per request (422) and documented on
every OpenAPI operation (`open_api_spec = False` on the middleware class opts
out). A required field applies to every request through the middleware. Any
other parameter after `req` fails at startup; `RequestBody`/`Files` are
endpoint-only.

For authentication, subclass `Authentication` and inherit its `middleware()`
handler. Only `user_loader()` and `roles_loader()` must be implemented.

Use locals or `current_request.set/get` for per-request data. The proxy also
exposes request/app and session lookup; `has_request_context()` checks availability.
Do not keep request-specific values on the middleware singleton.

Every HTTP request goes through the chain, but a middleware runs for unmatched
requests (404/405/redirects) only with `run_on_unmatched = True` and for static
files only with `run_on_static = True`. For unmatched requests check
`req.route_matched` (never read `req.route_handler`); their response is already
sent when `next()` returns, so add headers with `req.wrap_send(wrapper)`.
Authentication does not run for static files, so they are public. Sockets have
a separate path. `app.add_request_observer` gives complete HTTP records.

For credentialed CORS, declare specific frontend origins, methods and headers in
`CORS_ALLOW_ORIGINS`, `CORS_ALLOW_METHODS`, and `CORS_ALLOW_HEADERS`; enable
`CORS_ENABLED` and, when required, `CORS_ALLOW_CREDENTIALS`. Controller decorators
`cors`/`no_cors` provide overrides. CORS is not authentication or CSRF protection.

Sources: tutorial chapter 5; architecture chapter 9.
