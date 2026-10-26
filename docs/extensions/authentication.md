# Authentication

`patera-auth` provides an authentication and authorization middleware, with helpers for
cookies, JWT, roles and password hashing.

```sh
uv add "patera[auth]"
```

## The authentication middleware

Subclass `Authentication` and implement how users and roles are loaded:

```python
# app/middleware/auth_mw.py
import jwt

from patera import Request
from patera.auth import Authentication, AuthUtils
from patera.middleware import middleware


@middleware
class TokenAuth(Authentication):
    async def user_loader(self, req: Request):
        token = req.headers.get("authorization", "").removeprefix("Bearer ")
        try:
            claims = AuthUtils.validate_jwt_token(token, self.app.configs.SECRET_KEY)
        except jwt.InvalidTokenError:
            return None                    # -> not authenticated
        return await load_user(claims["sub"])

    async def roles_loader(self, user) -> list:
        return user.roles
```

- `user_loader(req)` returns the account or `None`; `roles_loader(user)` returns its role list.
- Mark the class with `@middleware` **without an order**: `Authentication` uses `-99`, inside the
  database session boundary, so loaders can use the database.
- Inject an account service for credential lookup.

## Protecting routes

```python
from patera.auth import login_required, role_required


@path("/account")
@login_required()                       # every endpoint requires a user
class AccountApi(Controller[App]):

    @get("/")
    async def me(self, req: Request) -> Response:
        return req.res.json({"user": req.user.name})

    @get("/admin")
    @role_required("admin", "owner")    # any of the listed roles
    async def admin(self, req: Request) -> Response: ...

    @get("/audit")
    @role_required("admin", "auditor", require_all=True)    # every listed role
    async def audit(self, req: Request) -> Response: ...
```

- A missing user raises `AuthenticationException` (`401`); missing roles raise
  `AuthorizationException` (`403`, the required roles in `data`). Both produce JSON error
  responses unless you [handle](../guide/exception-handling.md) them.
- `@role_required` implies authentication. Role requirements on the controller and on the
  endpoint must both be satisfied.
- Routes without the decorators **do not load the user**, even when cookies exist, and
  `ALWAYS_LOAD_ROLES` does not change that. Pages with optional login must load the account
  explicitly.
- The decorators do not protect [WebSockets](../guide/websockets.md) or
  [static files](../guide/static-files.md).
- Check object ownership in your services as well.

## Settings

The configuration model is `AuthConfig`, read from the field named after your subclass:

```python
from patera.auth import AuthConfig

class Config(BaseConfig):
    ...
    TOKEN_AUTH: AuthConfig = AuthConfig(
        AUTHENTICATION_ERROR_MSG="Please sign in",
        AUTHORIZATION_ERROR_MSG="Not allowed",
        ALWAYS_LOAD_ROLES=False,
    )
```

Override `refresh_credentials(res)` to renew cookies or tokens on responses.

## `AuthUtils`

| Helper | Description |
| --- | --- |
| `create_password_hash` / `check_password_hash` | bcrypt over a SHA-256 digest, so passwords of any length count in full; a malformed stored hash simply does not match; plain bcrypt hashes from earlier versions still verify |
| `password_hash_needs_update(hash)` | says when to re-hash after a successful login |
| `create_signed_cookie_value` / `decode_signed_cookie(value, key, max_age=None)` | HMAC with a signing timestamp; `max_age` rejects older values |
| `create_jwt_token` / `validate_jwt_token` | HS256; validation raises `jwt.InvalidTokenError` |

The password helpers are synchronous and deliberately slow; offload them with
`asyncio.to_thread` in async handlers.

!!! warning "Sessions and CSRF"

    Signed cookies detect tampering; they do not provide secrecy or revocation. For browser
    sessions choose cookie `Secure`/`HttpOnly`/`SameSite` deliberately, enforce CSRF protection on
    state-changing requests, and implement expiry and revocation. Patera's authentication
    metadata does not supply the application's whole session and CSRF policy. Catch expected
    credential failures, not every exception: a database outage is not bad credentials.
