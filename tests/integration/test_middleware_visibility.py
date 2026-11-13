"""
Which requests a middleware sees.

Every request goes through the middleware chain, including requests no route
matched (404, 405, trailing-slash redirects) and static resources. A
middleware runs for them only when it opts in with ``run_on_unmatched`` or
``run_on_static``; by default it is skipped, as it always was.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from patera import Request, Response
from patera.controller import Controller, get, path
from patera.middleware import MiddlewareBase, middleware

pytestmark = pytest.mark.integration


@path("/api")
class Items(Controller):
    @get("/items/")
    async def items(self, req: Request) -> Response:
        return req.res.json([])

    @get("/boom")
    async def boom(self, req: Request) -> Response:
        raise RuntimeError("boom")


FILES = {"static/hello.txt": b"hello\n"}


@middleware(order=10)
class Default(MiddlewareBase):
    """A middleware with the default flags."""

    seen: ClassVar[list[str]] = []

    async def middleware(self, req: Request) -> Response:
        type(self).seen.append(req.path)
        return await self.next(req)


class SeesEverything(MiddlewareBase):
    """An observability middleware: outermost, both flags, watches the send."""

    _order_: ClassVar[int] = -200
    _middleware: ClassVar[bool] = True
    run_on_unmatched: ClassVar[bool] = True
    run_on_static: ClassVar[bool] = True

    log: ClassVar[list[dict[str, Any]]] = []

    async def middleware(self, req: Request) -> Response:
        entry: dict[str, Any] = {
            "path": req.path,
            "matched": req.route_matched,
            "static": req.static_resource,
            "outcome": None
            if req.routing_outcome is None
            else req.routing_outcome.kind,
        }
        type(self).log.append(entry)

        def watch(send):
            async def watching_send(message):
                if message["type"] == "http.response.start":
                    entry["sent_status"] = message["status"]
                if message["type"] == "http.response.body" and not message.get(
                    "more_body", False
                ):
                    entry["body_done"] = True
                await send(message)

            return watching_send

        req.wrap_send(watch)
        try:
            res = await self.next(req)
        except Exception as exc:
            entry["raised"] = type(exc).__name__
            raise
        entry["returned_status"] = res.status_code
        entry["started_after_next"] = req.response_started
        if not req.route_matched:
            with pytest.raises(RuntimeError, match="No route matched"):
                _ = req.route_handler
        return res


@pytest.fixture(autouse=True)
def clear_logs():
    Default.seen.clear()
    SeesEverything.log.clear()


def make(make_app, **config):
    return make_app(
        controllers=[Items],
        middleware=[Default, SeesEverything],
        files=FILES,
        DEBUG=False,
        **config,
    )


async def test_default_middleware_skips_unmatched_and_static(make_app, client_for):
    app = make(make_app, STRICT_SLASHES=True)
    async with client_for(app) as client:
        assert (await client.get("/nowhere")).status_code == 404
        assert (await client.delete("/api/items/")).status_code == 405
        assert (
            await client.get("/api/items", follow_redirects=False)
        ).status_code == 308
        assert (await client.get("/static/hello.txt")).status_code == 200
        assert (await client.get("/api/items/")).status_code == 200
    assert Default.seen == ["/api/items/"]


async def test_flagged_middleware_sees_every_request(make_app, client_for):
    app = make(make_app, STRICT_SLASHES=True)
    async with client_for(app) as client:
        await client.get("/nowhere")
        await client.delete("/api/items/")
        await client.get("/api/items", follow_redirects=False)
        await client.get("/static/hello.txt")
        await client.get("/api/items/")
        await client.get("/api/boom")

    by_path = [(e["path"], e["outcome"], e["sent_status"]) for e in SeesEverything.log]
    assert by_path == [
        ("/nowhere", "not_found", 404),
        ("/api/items/", "method_not_allowed", 405),
        ("/api/items", "redirect", 308),
        ("/static/hello.txt", None, 200),
        ("/api/items/", None, 200),
        ("/api/boom", None, 500),
    ]
    not_found, not_allowed, redirect, static, ok, boom = SeesEverything.log

    # Unmatched: the response is sent in the innermost step; next() returns
    # the response with its status, and the response has started.
    for entry, status in ((not_found, 404), (not_allowed, 405), (redirect, 308)):
        assert entry["matched"] is False
        assert entry["returned_status"] == status
        assert entry["started_after_next"] is True
        assert entry["body_done"] is True

    assert static["static"] is True and static["matched"] is True
    assert static["body_done"] is True
    assert ok["returned_status"] == 200 and ok["static"] is False
    # An unhandled exception passes through the middleware; the 500 that
    # answers it still goes through the wrapped send channel.
    assert boom["raised"] == "RuntimeError"
    assert boom["body_done"] is True


async def test_flagged_middleware_can_answer_an_unmatched_request(make_app, client_for):
    class Maintenance(MiddlewareBase):
        _order_: ClassVar[int] = -200
        _middleware: ClassVar[bool] = True
        run_on_unmatched: ClassVar[bool] = True

        async def middleware(self, req: Request) -> Response:
            return req.res.json({"maintenance": True}).status(503)

    app = make_app(controllers=[Items], middleware=[Maintenance])
    async with client_for(app) as client:
        res = await client.get("/nowhere")
        assert res.status_code == 503
        assert res.json() == {"maintenance": True}
        assert (await client.get("/api/items/")).status_code == 503


async def test_head_to_unknown_path_through_flagged_middleware(make_app, client_for):
    app = make(make_app)
    async with client_for(app) as client:
        res = await client.head("/nowhere")
    assert res.status_code == 404
    assert res.content == b""
    assert res.headers["content-length"] == "49"


def test_flags_default_to_off():
    assert MiddlewareBase.run_on_unmatched is False
    assert MiddlewareBase.run_on_static is False


def test_unmatched_request_has_no_route_handler(make_app):
    from tests.helpers import make_request

    app = make_app()
    req = make_request(app, "GET", "/nowhere")
    req.route_matched = False
    with pytest.raises(RuntimeError, match="No route matched GET /nowhere"):
        _ = req.route_handler
