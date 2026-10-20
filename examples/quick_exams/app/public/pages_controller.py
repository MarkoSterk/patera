from patera import Request, Response
from patera.controller import Controller, get, path
from app import App


@path("/")
class Pages(Controller[App]):
    @get("/")
    async def index(self, req: Request, exam_id: str = "") -> Response:
        req.res.set_header("Referrer-Policy", "no-referrer")
        req.res.set_header("Cache-Control", "no-store")
        req.res.set_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        return await req.res.html("index.html")

    @get("/exam/<exam_id>")
    async def exam(self, req: Request, exam_id: str) -> Response:
        return await self.index(req, exam_id)
