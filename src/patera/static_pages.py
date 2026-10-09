from __future__ import annotations
from typing import TYPE_CHECKING, Any  # noqa: F401
from pathlib import Path
from .media_types import MediaType
from .controller import Controller, get, produces, after_init
from .request import Request
from .response import Response
from .exceptions import StaticPageNotFound

if TYPE_CHECKING:
    from .patera import Patera  # noqa: F401


STATIC_PAGES_TEMPLATE_PREFIX = "__static_pages__"


class StaticPages(Controller["Patera[Any]"]):
    @after_init
    def add_template_path(self) -> None:
        """
        Registers the static pages folder with Jinja2.

        Requested pages are rendered through a private template prefix, so an
        app template with the same name (e.g. templates/index.html) can never
        be served instead of the page and vice versa. The folder is also added
        to the regular search path, after the app templates, so pages can
        extend/include each other by name.
        """
        pages_path = str(self.static_pages_path)
        self.app.add_template_prefix(STATIC_PAGES_TEMPLATE_PREFIX, pages_path)
        self.app.add_template_path(pages_path)

    @get("/<path:page>")
    @produces(MediaType.TEXT_HTML)
    async def get(self, req: Request, page: str) -> Response:
        """
        Endpoint for static pages.
        """

        if not page.endswith(".html"):
            page += ".html"

        path = (self.static_pages_path / page).resolve()

        if not path.is_relative_to(self.static_pages_path):
            raise StaticPageNotFound(page)

        if not path.is_file():
            raise StaticPageNotFound(page)

        template_name = path.relative_to(self.static_pages_path).as_posix()
        return await req.res.html(f"{STATIC_PAGES_TEMPLATE_PREFIX}/{template_name}")

    @property
    def static_pages_path(self) -> Path:
        path: Path = Path(
            self.app.root_path
        ) / self.app.configs.STATIC_PAGES_DIR.lstrip("/\\")
        return path.resolve()
