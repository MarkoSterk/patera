from typing import TYPE_CHECKING

from patera import Request, Response
from patera.controller import Controller, after_request, get, path

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)


@path("/", open_api_spec=False)
class Pages(Controller["App"]):
    @get("/")
    async def index(self, req: Request) -> Response:
        return await req.res.html("index.html")

    @get("/exam/<exam_id>")
    async def exam(self, req: Request, exam_id: str) -> Response:
        return await req.res.html("index.html")

    @get("/admin")
    async def admin(self, req: Request) -> Response:
        return req.res.redirect(
            self.app.url_for("_AdminController.dashboard", lang="en")
        )

    @after_request
    def security_headers(self, res: Response) -> None:
        res.set_headers(
            {
                "Content-Security-Policy": CONTENT_SECURITY_POLICY,
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            }
        )
