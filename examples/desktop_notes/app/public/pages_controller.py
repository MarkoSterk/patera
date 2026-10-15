from patera import MediaType, Request, Response
from patera.controller import Controller, get, path, produces
from patera.desktop import settings_file

from app import App
from app.configs import DATA_FOLDER


@path("/")
class PagesController(Controller[App]):
    @get("/")
    @produces(MediaType.TEXT_HTML)
    async def index(self, req: Request) -> Response:
        """The notes page, which the window opens (DESKTOP.INDEX_PAGE)."""
        return await req.res.html(
            "index.html",
            context={
                "data_folder": str(DATA_FOLDER),
                "settings_file": str(settings_file(self.app.app_name)),
            },
        )
