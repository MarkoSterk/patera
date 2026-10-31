from typing import TYPE_CHECKING

from patera.desktop import settings_file, user_data_dir

from patera import MediaType, Request, Response
from patera.controller import Controller, get, path, produces

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


@path("/")
class PagesController(Controller["App"]):
    @get("/")
    @produces(MediaType.TEXT_HTML)
    async def index(self, req: Request) -> Response:
        """The notes page, which the window opens (DESKTOP.INDEX_PAGE)."""
        return await req.res.html(
            "index.html",
            context={
                "data_folder": str(user_data_dir(self.app.app_name)),
                "settings_file": str(settings_file(self.app.app_name)),
            },
        )
