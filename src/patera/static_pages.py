from __future__ import annotations
from typing import TYPE_CHECKING, Any  # noqa: F401
import os

from .media_types import MediaType
from .controller import Controller, get, produces
from .request import Request
from .response import Response

if TYPE_CHECKING:
    from .patera import Patera  # noqa: F401


class StaticPages(Controller["Patera[Any]"]):
    def init(self) -> None:
        """
        Add template path to Jinja2 templates search path.
        """
        path: str = os.path.join(
            self.app.root_path, self.app.configs.STATIC_PAGES_DIR.lstrip("/\\")
        )
        self.app.add_template_path(path)

    @get("/<path:page>")
    @produces(MediaType.TEXT_HTML)
    async def get(self, req: Request, page: str) -> Response:
        """
        Endpoint for static pages.
        """

        if not page.endswith(".html"):
            page += ".html"

        return await req.res.html(page)
