"""
req.on_finish: callbacks that run once a request is finished, after its
response was sent completely, it failed, or the client left.
"""

from __future__ import annotations

from typing import Any

import pytest

from patera import Request, Response
from patera.controller import Controller, get, path, post
from patera.exceptions.runtime_exceptions import ClientDisconnected
from patera.middleware import MiddlewareBase, middleware

from tests.helpers import make_receive, make_scope

pytestmark = pytest.mark.integration

EVENTS: list[Any] = []


@path("/api")
class Things(Controller):
    @get("/plain")
    async def plain(self, req: Request) -> Response:
        req.on_finish(lambda exc: EVENTS.append(("finished", exc)))
        return req.res.json({"ok": True})

    @get("/stream")
    async def stream(self, req: Request) -> Response:
        req.on_finish(lambda exc: EVENTS.append(("finished", exc)))

        async def chunks():
            for chunk in (b"a", b"b"):
                EVENTS.append(("chunk", chunk))
                yield chunk

        return req.res.stream(chunks())

    @post("/upload")
    async def upload(self, req: Request) -> Response:
        req.on_finish(lambda exc: EVENTS.append(("finished", exc)))
        await req.body()
        return req.res.json({})

    @get("/boom")
    async def boom(self, req: Request) -> Response:
        req.on_finish(lambda exc: EVENTS.append(("finished", exc)))
        raise RuntimeError("boom")


@middleware(order=1)
class Finishes(MiddlewareBase):
    run_on_unmatched = True

    async def middleware(self, req: Request) -> Response:
        def failing(exc):
            raise ValueError("callback failed")

        req.on_finish(failing)
        req.on_finish(lambda exc: EVENTS.append(("middleware", req.path)))
        return await self.next(req)


@pytest.fixture(autouse=True)
def clear():
    EVENTS.clear()


@pytest.fixture
def app(make_app):
    return make_app(controllers=[Things], middleware=[Finishes], DEBUG=False)


async def test_callbacks_run_after_the_response(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/api/plain")).status_code == 200
    # Registration order; the failing callback is logged and skipped.
    assert EVENTS == [("middleware", "/api/plain"), ("finished", None)]


async def test_callbacks_run_after_a_streamed_body(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/api/stream")).content == b"ab"
    assert EVENTS == [
        ("chunk", b"a"),
        ("chunk", b"b"),
        ("middleware", "/api/stream"),
        ("finished", None),
    ]


async def test_callbacks_run_for_unmatched_requests(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/nowhere")).status_code == 404
    assert EVENTS == [("middleware", "/nowhere")]


async def test_a_handled_error_is_not_an_escaping_exception(app, client_for):
    async with client_for(app) as client:
        assert (await client.get("/api/boom")).status_code == 500
    assert ("finished", None) in EVENTS


async def test_a_client_disconnect_is_reported(app):
    app.build()
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    await app(
        make_scope("POST", "/api/upload"),
        make_receive(b"partial", disconnect=True),
        send,
    )
    assert sent == []  # nobody left to answer
    finished = [exc for name, exc in EVENTS if name == "finished"]
    assert len(finished) == 1 and isinstance(finished[0], ClientDisconnected)


async def test_an_exception_raised_to_the_server_is_reported(make_app):
    app = make_app(controllers=[Things], DEBUG=True)
    app.build()

    async def send(message):
        pass

    with pytest.raises(RuntimeError, match="boom"):
        await app(make_scope("GET", "/api/boom"), make_receive(), send)
    finished = [exc for name, exc in EVENTS if name == "finished"]
    assert len(finished) == 1 and isinstance(finished[0], RuntimeError)
