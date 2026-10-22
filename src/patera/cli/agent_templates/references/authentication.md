# Authentication and authorization

Install `patera-auth`. Subclass `Authentication` from `patera.auth` and implement
both `async def user_loader(self, req)` and `async def roles_loader(self, user)`.
The former returns the account or None; the latter returns its role list. Inject
an account service for credential lookup. Mark the class with `@middleware`
without an order: Authentication inherits -99, inside the database boundary.
Place it in a discoverable `middleware/*_middleware.py` module. Its configuration
model is exported as `AuthConfig`. HTTP metadata selects protected routes:

```python
from patera.auth import login_required, role_required

@get("/account")
@login_required()
async def account(self, req: Request) -> Response:
    return req.res.json({"id": req.user.id})
```

This is a method fragment inside a controller with normal HTTP imports.
`@role_required("editor", "admin")` accepts any role in that group and implies
authentication. Controller and method groups must both pass; `require_all=True`
requires every role in a group. Check object ownership in a service as well.

Public routes without auth metadata skip user loading, even when cookies exist;
`ALWAYS_LOAD_ROLES` does not change that. Optional-login pages must load accounts
explicitly. HTTP auth decorators do not protect sockets or static files.

`AuthUtils.create_password_hash` and `check_password_hash` are synchronous bcrypt
helpers; offload expensive work with `asyncio.to_thread` in async handlers.
`password_hash_needs_update` supports migrating legacy hashes after successful
login. Signed cookies detect tampering, not secrecy or revocation; use `max_age`
when decoding. JWT validation raises on invalid/expired tokens. Catch expected
credential failures, not every exception (a database outage is not bad credentials).

For browser sessions choose cookie Secure/HttpOnly/SameSite deliberately, enforce
CSRF on state-changing requests, and implement expiry and revocation. Patera's
authentication metadata alone does not supply the application's entire session
and CSRF policy. Test 401, 403, ownership failures, logout and public behavior.

Sources: tutorial chapters 10 and 18; architecture chapter 17.
