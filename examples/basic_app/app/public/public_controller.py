from patera.controller import Controller, path, get, produces
from patera import Request, Response, HttpStatus, MediaType, ignore

from app import App


@path("/")
@ignore
class PublicController(Controller[App]):
    @get("/")
    @produces(MediaType.TEXT_HTML)
    async def index(self, req: Request) -> Response:
        return (
            await req.res.html(
                "index.html",
                context={
                    "app_name": self.app.configs.APP_NAME,
                    "app_version": self.app.configs.APP_VERSION,
                },
            )
        ).status(HttpStatus.OK)
