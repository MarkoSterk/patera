from __future__ import annotations

from .media_types import MediaType
from .controller import Controller, get, produces
from .request import Request
from .response import Response


class StaticPages(Controller):
    @get("/<path:page>")
    @produces(MediaType.TEXT_HTML)
    async def get(self, req: Request, page: str) -> Response:
        """
        Endpoint for static pages.
        """

        if not page.endswith(".html"):
            page += ".html"

        page = self.app.configs.STATIC_PAGES_DIR + "/" + page
        return await req.res.html(page)
