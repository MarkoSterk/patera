"""
Request observers: the application reports every finished HTTP request.
"""

from __future__ import annotations

import pytest

from patera import Request, RequestRecord, Response, abort
from patera.controller import Controller, get, path
from patera.router import Router

pytestmark = pytest.mark.integration


@path("/items")
class Items(Controller):
    @get("/<int:item_id>")
    async def item(self, req: Request, item_id: int) -> Response:
        if item_id == 0:
            abort("No such item", 404)
        return req.res.json({"id": item_id})

    @get("/broken")
    async def broken(self, req: Request) -> Response:
        raise RuntimeError("boom")


async def test_observers_receive_every_request(make_app, client_for):
    app = make_app(controllers=[Items], DEBUG=False)
    records: list[RequestRecord] = []
    app.add_request_observer(records.append)

    def failing_observer(record: RequestRecord) -> None:
        raise ValueError("observer bug")

    app.add_request_observer(failing_observer)

    async with client_for(app) as client:
        assert (await client.get("/items/7")).status_code == 200
        assert (await client.get("/items/0")).status_code == 404
        assert (await client.get("/items/broken")).status_code == 500
        assert (await client.get("/nowhere")).status_code == 404
        assert (await client.post("/items/7")).status_code == 405

    seen = [(r.method, r.path, r.route, r.status_code) for r in records]
    assert seen == [
        ("GET", "/items/7", "/items/<int:item_id>", 200),
        ("GET", "/items/0", "/items/<int:item_id>", 404),
        ("GET", "/items/broken", "/items/broken", 500),
        ("GET", "/nowhere", None, 404),
        ("POST", "/items/7", None, 405),
    ]
    assert all(r.duration >= 0 and r.started_at > 0 for r in records)


async def test_a_request_that_raises_is_recorded_as_500(make_app, client_for):
    app = make_app(controllers=[Items], DEBUG=True)
    records: list[RequestRecord] = []
    app.add_request_observer(records.append)
    async with client_for(app) as client:
        # In debug mode the error propagates to the server, which answers 500.
        with pytest.raises(RuntimeError):
            await client.get("/items/broken")
    assert [r.status_code for r in records] == [500]


async def test_without_observers_nothing_is_recorded(make_app, client_for):
    app = make_app(controllers=[Items])
    async with client_for(app) as client:
        assert (await client.get("/items/7")).status_code == 200
    assert app._request_observers == []


def test_router_reports_the_rule_of_an_endpoint():
    router = Router()

    def handler():
        return None

    def other():
        return None

    router.add_route("/a/<int:id>", handler, ["GET"], "A.get")
    router.add_route("/a-alias/<int:id>", handler, ["GET"], "A.alias")
    assert router.path_of(handler) == "/a/<int:id>"
    assert router.path_of(other) is None
