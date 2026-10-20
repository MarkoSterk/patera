from typing import Any, Optional

from patera import Request
from patera.auth import Authentication
from patera.injectable import Inject
from patera.middleware import middleware

from ..models import User
from ..services.accounts import AccountService


def access_token(req: Request, cookie_name: str) -> str:
    """The JWT from ``Authorization: Bearer ...`` (API clients) or the auth cookie (browser)."""
    scheme, _, token = req.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return req.cookies.get(cookie_name, "")


@middleware
class JwtAuthentication(Authentication):
    """
    Stateless authentication with signed JWT access tokens. It runs only for
    endpoints marked with @login_required or @role_required; Patera Admin
    marks its own endpoints with the Admin permissions.
    """

    accounts: Inject[AccountService]

    async def user_loader(self, req: Request) -> Optional[User]:
        token = access_token(req, self.app.configs.AUTH_COOKIE_NAME)
        return await self.accounts.user_from_token(token)

    async def roles_loader(self, user: Any) -> list[Any]:
        return self.accounts.roles_of(user)
