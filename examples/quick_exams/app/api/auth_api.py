from typing import TYPE_CHECKING

from app.schemas import LoginIn, PasswordChangeIn, TokenOut, UserOut
from app.services.accounts import AccountService
from patera.auth import login_required
from patera.database.sql import transactional

from patera import MediaType, Request, Response
from patera.controller import Controller, consumes, get, path, post, RequestBody
from patera.injectable import Inject

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/api/auth", tags=["Authentication"])
class AuthApi(Controller["App"]):
    """
    JWT sign-in for the workspace, Patera Admin and API clients. The token is
    returned in the body and set in an HttpOnly, SameSite=Strict cookie.
    """

    accounts: Inject[AccountService]

    @post("/login")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def login(
        self, req: Request, data: RequestBody[LoginIn]
    ) -> Response[TokenOut]:
        user = await self.accounts.authenticate(data.email, data.password)
        return self._signed_in(req, user)

    @post("/password")
    @consumes(MediaType.APPLICATION_JSON)
    @login_required()
    @transactional
    async def change_password(
        self, req: Request, data: RequestBody[PasswordChangeIn]
    ) -> Response[TokenOut]:
        """
        Changes the signed-in user's password. Every earlier token stops
        working; this browser receives a new one, so it stays signed in.
        """
        user = await self.accounts.change_password(
            req.user.id, data.current_password, data.new_password
        )
        return self._signed_in(req, user)

    def _signed_in(self, req: Request, user) -> Response[TokenOut]:
        """A fresh token for ``user``, in the body and in the auth cookie."""
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
