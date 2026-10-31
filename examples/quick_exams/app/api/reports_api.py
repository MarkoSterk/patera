from typing import TYPE_CHECKING

from app.models import INSTRUCTOR
from app.schemas import ReportOut
from app.services.reports import ReportService
from patera.auth import role_required

from patera import Request, Response
from patera.controller import Controller, get, path
from patera.injectable import Inject

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/api/reports", tags=["Reports"])
@role_required(INSTRUCTOR)
class ReportsApi(Controller["App"]):
    reports: Inject[ReportService]

    @get("/")
    async def own_reports(self, req: Request) -> Response[list[ReportOut]]:
        return req.res.json(await self.reports.reports(req.user.id))
