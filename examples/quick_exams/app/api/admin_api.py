from typing import TYPE_CHECKING

from app.models import ADMIN
from app.schemas import AdminOverviewOut, UserIn, UserOut
from app.services.accounts import AccountService
from app.services.reports import ReportService
from patera.auth import role_required
from patera.database.sql import transactional

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import Controller, consumes, get, path, post, produces, put
from patera.injectable import Inject

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/api/admin", tags=["Administration"])
@role_required(ADMIN)
class AdminApi(Controller["App"]):
    accounts: Inject[AccountService]
    reports: Inject[ReportService]

    @get("/overview")
    async def overview(self, req: Request) -> Response[AdminOverviewOut]:
        return req.res.json(
            {
                "users": await self.accounts.list_users(),
                "counts": await self.reports.counts(),
                "reports": await self.reports.reports(),
            }
        )

    @post("/users")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create_user(self, req: Request, data: UserIn) -> Response[UserOut]:
        user = await self.accounts.create_user(data)
        return req.res.json(user)

    @put("/users/<user_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @transactional
    async def update_user(
        self, req: Request, user_id: str, data: UserIn
    ) -> Response[UserOut]:
        user = await self.accounts.update_user(user_id, data)
        return req.res.json(user)
