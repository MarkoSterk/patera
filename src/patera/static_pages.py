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


class StaticPages(Controller["Patera[Any]"]):
    @after_init
    def add_template_path(self) -> None:
        """
        Add template path to Jinja2 templates search path.
        """

        self.app.add_template_path(str(self.static_pages_path))

    @get("/<path:page>")
    @produces(MediaType.TEXT_HTML)
    async def get(self, req: Request, page: str) -> Response:
        """
        Endpoint for static pages.
        """

        if not page.endswith(".html"):
            page += ".html"

        path = self.static_pages_path / page
        if not path.exists():
            raise StaticPageNotFound(page)

        return await req.res.html(page)

    @property
    def static_pages_path(self) -> Path:
        path: Path = Path(
            self.app.root_path
        ) / self.app.configs.STATIC_PAGES_DIR.lstrip("/\\")
        path.resolve()
        return path
