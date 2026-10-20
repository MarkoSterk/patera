from patera import Request, Response
from patera.auth import role_required
from patera.controller import Controller, get, path
from patera.injectable import Inject

from app import App
from app.models import INSTRUCTOR
from app.schemas import ReportOut
from app.services.reports import ReportService


@path("/api/reports", tags=["Reports"])
@role_required(INSTRUCTOR)
class ReportsApi(Controller[App]):
    reports: Inject[ReportService]

    @get("/")
    async def own_reports(self, req: Request) -> Response[list[ReportOut]]:
        return req.res.json(await self.reports.reports(req.user.id))
