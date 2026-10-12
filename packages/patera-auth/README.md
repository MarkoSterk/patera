# patera-auth

Authentication and authorization middleware for Patera: cookies, JWT, roles and password hashing. Part of [Patera](https://github.com/MarkoSterk/Patera), a modular async-first Python web framework.

## Installation

```sh
pip install patera-auth
# or, with uv
uv add "patera[auth]"
```

Requires Python 3.13 or newer and `patera>=0.121`.

## Usage

`patera-auth` provides an authentication middleware. Implement how users and roles are loaded:

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

See the [Authentication section of the Patera documentation](https://github.com/MarkoSterk/Patera#authentication) for the full guide.

## License

MIT. See [LICENSE](https://github.com/MarkoSterk/Patera/blob/main/LICENSE).
