from patera import MediaType, Request, Response
from patera.auth import login_required
from patera.controller import Controller, consumes, get, path, post
from patera.database.sql import transactional
from patera.injectable import Inject

from app import App
from app.schemas import LoginIn, TokenOut, UserOut
from app.services.accounts import AccountService


@path("/api/auth", tags=["Authentication"])
class AuthApi(Controller[App]):
    """
    JWT sign-in for the workspace, Patera Admin and API clients. The token is
    returned in the body and set in an HttpOnly, SameSite=Strict cookie.
    """

    accounts: Inject[AccountService]

    @post("/login")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def login(self, req: Request, data: LoginIn) -> Response[TokenOut]:
        user = await self.accounts.authenticate(data.email, data.password)
        token = self.accounts.issue_token(user)
        configs = self.app.configs
        return req.res.json(
            {
                "token": token,
                "expires_in": configs.JWT_LIFETIME_SECONDS,
                "user": user,
            }
        ).set_cookie(
            configs.AUTH_COOKIE_NAME,
            token,
            max_age=configs.JWT_LIFETIME_SECONDS,
            secure=configs.secure_cookies,
            http_only=True,
            same_site="Strict",
        )

    # GET because Patera Admin's logout button calls it with fetch().
    @get("/logout")
    async def logout(self, req: Request) -> Response:
        configs = self.app.configs
        return req.res.no_content().delete_cookie(
            configs.AUTH_COOKIE_NAME, same_site="Strict", secure=configs.secure_cookies
        )

    @get("/me")
    @login_required()
    async def me(self, req: Request) -> Response[UserOut]:
        return req.res.json(req.user)
