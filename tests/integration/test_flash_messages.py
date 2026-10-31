from __future__ import annotations

import pytest

from patera import Request, Response
from patera.base_extension import BaseExtension
from patera.controller import Controller, get, path
from patera.middleware import MiddlewareBase, middleware


pytestmark = pytest.mark.integration


@middleware(order=1)
class FlashMiddleware(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        if req.path == "/flash":
            self.flash_message("Middleware", "info")
        return await self.next(req)


@path("/")
class FlashController(Controller):
    @get("/flash")
    async def flash(self, req: Request) -> Response:
        BaseExtension(self.app).flash_message("Extension", "success")
        self.flash_message("Controller")
        self.app.flash_message("Application", "info")
        return await req.res.html("flash.html")

    @get("/empty")
    async def empty(self, req: Request) -> Response:
        return await req.res.html("flash.html")


async def test_all_components_share_request_messages(make_app, client_for):
    app = make_app(
        controllers=[FlashController],
        middleware=[FlashMiddleware],
        files={
            "templates/flash.html": "{% for message, status in flashed_messages %}"
            "{{ message }}:{{ status or '' }};{% endfor %}"
        },
    )
    async with client_for(app) as client:
        response = await client.get("/flash")
        assert response.status_code == 200
        assert (
            response.text
            == "Middleware:info;Extension:success;Controller:;Application:info;"
        )
        response = await client.get("/empty")
        assert response.status_code == 200
        assert response.text == ""
