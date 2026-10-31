from typing import TYPE_CHECKING

from patera import HttpStatus, MediaType, Request, Response
from patera.controller import Controller, get, path, produces

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/")
class PublicController(Controller["App"]):
    @get("/")
    @produces(MediaType.TEXT_HTML)
    async def index(self, req: Request) -> Response:
        return (
            await req.res.html(
                "index.html",
                context={
                    "app_name": self.app.configs.APP_NAME,
                    "app_version": self.app.configs.VERSION,
                },
            )
        ).status(HttpStatus.OK)
