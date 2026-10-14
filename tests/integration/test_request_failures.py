"""
Failures around a request: errors after the response started, clients that
disconnect, validation errors that are not the client's, form lists and
undecodable query strings.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest
from pydantic import BaseModel

from patera import MediaType, Request, Response
from patera.controller import Controller, consumes, get, path, post, socket

from tests.helpers import make_scope

pytestmark = pytest.mark.integration


class Tags(BaseModel):
    tags: list[str]
    labels: Optional[set[str]] = None
    note: str = ""


class Out(BaseModel):
    count: int


SEEN: dict[str, Any] = {}


@path("/f")
class FailuresController(Controller):
    @get("/stream")
    async def stream(self, req: Request) -> Response:
        def rows():
            yield {"a": 1}
            raise RuntimeError("database went away")

        return req.res.ndjson(rows())

    @post("/body")
    async def body(self, req: Request) -> Response:
        SEEN["body"] = await req.body()
        return req.res.json({"length": len(SEEN["body"])})

    @get("/server-data")
    async def server_data(self, req: Request) -> Response:
        # Data from a database or another service that does not fit.
        Out.model_validate({"count": "secret-value"})
        return req.res.json({})

    @post("/tags")
    @consumes(MediaType.APPLICATION_X_WWW_FORM_URLENCODED)
    async def tags(self, req: Request, data: Tags) -> Response:
        return req.res.json(data.model_dump(mode="json"))

    @get("/query")
    async def query(self, req: Request) -> Response:
        return req.res.json({"q": req.query_string})


async def call(app, scope, messages=()):
    """Runs one raw ASGI request and returns the messages the app sent."""
    pending = list(messages) or [
        {"type": "http.request", "body": b"", "more_body": False}
    ]
    sent: list[dict[str, Any]] = []
    started = False

    async def receive():
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message):
        nonlocal started
        if message["type"] == "http.response.start":
            # Real servers refuse a second start.
            assert not started, "the response was started twice"
            started = True
        sent.append(message)

    raised: Optional[BaseException] = None
    try:
        await app(scope, receive, send)
    except Exception as exc:  # noqa: BLE001
        raised = exc
    return sent, raised


@pytest.fixture
def app(make_app):
    application = make_app(controllers=[FailuresController], DEBUG=False)
    application.build()
    return application


async def test_an_error_after_the_response_started_closes_the_connection(app):
    sent, raised = await call(app, make_scope("GET", "/f/stream"))
    # No second response: the original error goes to the server, which
    # closes the connection, so the client sees an incomplete body.
    assert isinstance(raised, RuntimeError)
    assert str(raised) == "database went away"
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]
    assert sent[-1]["body"] == b'{"a":1}\n'


async def test_a_client_that_disconnects_mid_body_gets_no_response(app):
    SEEN.clear()
    sent, raised = await call(
        app,
        make_scope("POST", "/f/body", headers={"content-length": "10"}),
        [
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.disconnect"},
        ],
    )
    assert raised is None
    assert sent == []
    assert "body" not in SEEN  # the handler never saw the partial body


async def test_validation_errors_outside_request_bodies_are_server_errors(
    app, client_for
):
    async with client_for(app) as client:
        res = await client.get("/f/server-data")
    assert res.status_code == 500
    assert "secret-value" not in res.text


async def test_a_single_form_value_fills_a_list_field(app, client_for):
    async with client_for(app) as client:
        one = await client.post("/f/tags", data={"tags": "a", "labels": "x"})
        two = await client.post("/f/tags", data={"tags": ["a", "b"]})
        none = await client.post("/f/tags", data={"note": "n"})
    assert one.status_code == 200, one.text
    assert one.json() == {"tags": ["a"], "labels": ["x"], "note": ""}
    assert two.json()["tags"] == ["a", "b"]
    assert none.status_code == 422
    assert none.json()["data"][0]["loc"] == ["tags"]


async def test_raw_bytes_in_the_query_string_do_not_fail_the_request(app):
    sent, raised = await call(
        app, make_scope("GET", "/f/query", query_string=b"a=\xff")
    )
    assert raised is None
    assert sent[0]["status"] == 200


class _FakeSession:
    closed = False

    async def close(self) -> None:
        self.closed = True


SOCKET_SESSIONS: list[_FakeSession] = []


@path("/ws")
class SocketController(Controller):
    @socket("/echo")
    async def echo(self, req: Request) -> None:
        from patera.ctx import ActiveSessions, get_request_context

        # What Model.query() does inside a socket handler.
        ctx = get_request_context()
        ctx.sessions = ActiveSessions()
        session = _FakeSession()
        ctx.sessions.set_session("session", session)  # type: ignore[arg-type]
        SOCKET_SESSIONS.append(session)
        await req.receive()
        await req.accept()


async def test_socket_handlers_get_their_sessions_closed(make_app):
    app = make_app(controllers=[SocketController], DEBUG=False)
    app.build()
    scope = {**make_scope("GET", "/ws/echo"), "type": "websocket"}
    sent: list[dict[str, Any]] = []
    messages = [{"type": "websocket.connect"}]

    async def receive():
        return messages.pop(0) if messages else {"type": "websocket.disconnect"}

    async def send(message):
        sent.append(message)

    SOCKET_SESSIONS.clear()
    await app(scope, receive, send)
    assert sent[0]["type"] == "websocket.accept"
    assert SOCKET_SESSIONS and SOCKET_SESSIONS[0].closed
