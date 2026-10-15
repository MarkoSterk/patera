from __future__ import annotations

import asyncio

import pytest
from asgi_lifespan import LifespanManager

from patera import Patera, Request, Response, on_shutdown, on_startup
from patera.controller import Controller, get, path, socket
from patera.middleware import MiddlewareBase, middleware

from tests.helpers import make_request

pytestmark = pytest.mark.integration

PNG = bytes(range(256)) * 4  # 1024 bytes of binary data


async def test_static_files_full_and_ranges(make_app, client_for):
    app = make_app(
        files={
            "static/data.bin": PNG,
            "static/css/site.css": "body{}",
            "static/dir/.keep": "",
        }
    )
    async with client_for(app) as client:
        res = await client.get("/static/css/site.css")
        assert res.status_code == 200
        assert res.text == "body{}"
        assert res.headers["content-type"].startswith("text/css")
        assert res.headers["accept-ranges"] == "bytes"

        res = await client.get("/static/data.bin", headers={"range": "bytes=10-19"})
        assert res.status_code == 206
        assert res.content == PNG[10:20]
        assert res.headers["content-range"] == "bytes 10-19/1024"
        assert res.headers["content-length"] == "10"
        # one content-type header only
        assert res.headers.get_list("content-type") == ["application/octet-stream"]

        res = await client.get("/static/data.bin", headers={"range": "bytes=1000-"})
        assert res.content == PNG[1000:]

        res = await client.get("/static/data.bin", headers={"range": "bytes=-4"})
        assert res.status_code == 206
        assert res.content == PNG[-4:]

        res = await client.get("/static/data.bin", headers={"range": "bytes=5000-6000"})
        assert res.status_code == 416
        assert res.headers["content-range"] == "bytes */1024"

        # Directories and missing files are 404, path traversal is blocked
        assert (await client.get("/static/dir")).status_code == 404
        assert (await client.get("/static/missing.txt")).status_code == 404
        assert (await client.get("/static/../__init__.py")).status_code == 404


async def test_static_files_are_cacheable(make_app, client_for):
    app = make_app(files={"static/data.bin": PNG})
    async with client_for(app) as client:
        full = await client.get("/static/data.bin")
        etag = full.headers["etag"]
        assert full.status_code == 200
        assert full.content == PNG
        assert full.headers["last-modified"].endswith("GMT")
        assert full.headers["cache-control"] == "public, max-age=300"

        # Ranges and errors carry the same validator as the full file
        part = await client.get("/static/data.bin", headers={"range": "bytes=0-9"})
        assert part.headers["etag"] == etag
        bad = await client.get("/static/data.bin", headers={"range": "bytes=9000-"})
        assert bad.status_code == 416
        assert bad.headers["etag"] == etag

        res = await client.get("/static/data.bin", headers={"if-none-match": etag})
        assert res.status_code == 304
        assert res.content == b""
        assert res.headers["etag"] == etag
        assert "content-type" not in res.headers
        res = await client.get(
            "/static/data.bin", headers={"if-none-match": f'W/"other", {etag}'}
        )
        assert res.status_code == 304
        res = await client.get("/static/data.bin", headers={"if-none-match": "*"})
        assert res.status_code == 304
        res = await client.get("/static/data.bin", headers={"if-none-match": '"x"'})
        assert res.status_code == 200

        since = full.headers["last-modified"]
        res = await client.get("/static/data.bin", headers={"if-modified-since": since})
        assert res.status_code == 304
        res = await client.get(
            "/static/data.bin",
            headers={"if-modified-since": "Thu, 01 Jan 1970 00:00:00 GMT"},
        )
        assert res.status_code == 200
        # If-None-Match takes precedence over If-Modified-Since
        res = await client.get(
            "/static/data.bin",
            headers={"if-none-match": '"x"', "if-modified-since": since},
        )
        assert res.status_code == 200

        # If-Range: a matching validator gives the range, a stale one the full file
        res = await client.get(
            "/static/data.bin", headers={"range": "bytes=0-9", "if-range": etag}
        )
        assert res.status_code == 206
        res = await client.get(
            "/static/data.bin", headers={"range": "bytes=0-9", "if-range": '"old"'}
        )
        assert res.status_code == 200
        assert res.content == PNG


async def test_missing_static_file_is_a_json_404(make_app, client_for):
    app = make_app(files={"static/a.txt": "a"})
    async with client_for(app) as client:
        res = await client.get("/static/missing.txt")
        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/json")
        assert res.json()["status"] == "error"


def test_full_files_are_sent_zero_copy(make_app, tmp_path):
    from patera.utilities import file_response

    target = tmp_path / "big.bin"
    target.write_bytes(PNG)
    app = make_app()
    req = make_request(app)
    res = file_response(req.res, str(target), req.headers)
    assert res.zero_copy == {"file_path": str(target), "start": 0, "length": len(PNG)}


async def test_static_pages(make_app, client_for):
    app = make_app(
        USE_STATIC_PAGES=True,
        STATIC_PAGES_DIR="pages",
        STATIC_PAGES_URL="/pages",
        files={
            "pages/about.html": "<p>About {{ app.app_name }}</p>",
            "pages/docs/intro.html": "intro",
        },
    )
    async with client_for(app) as client:
        assert (await client.get("/pages/about")).text == "<p>About Test app</p>"
        assert (await client.get("/pages/about.html")).status_code == 200
        assert (await client.get("/pages/docs/intro")).text == "intro"
        assert (await client.get("/pages/missing")).status_code == 404
        assert app.url_for("static_pages", page="docs/intro") == "/pages/docs/intro"
        assert (await client.get("/pages/../__init__")).status_code == 404


@path("/home")
class HomeController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return await req.res.html("index.html")


async def test_static_pages_do_not_shadow_app_templates(make_app, client_for):
    app = make_app(
        controllers=[HomeController],
        USE_STATIC_PAGES=True,
        STATIC_PAGES_DIR="pages",
        STATIC_PAGES_URL="/pages",
        files={
            "templates/index.html": "template index",
            "pages/index.html": "page index",
            "pages/layout.html": "[{% block body %}{% endblock %}]",
            "pages/child.html": "{% extends 'layout.html' %}{% block body %}child{% endblock %}",
        },
    )
    async with client_for(app) as client:
        assert (await client.get("/home/")).text == "template index"
        assert (await client.get("/pages/index")).text == "page index"
        assert (await client.get("/pages/child")).text == "[child]"


class LifecycleApp(Patera):
    events: list[str]

    @on_startup
    async def b_start(self):
        self.events.append("b_start")

    @on_startup
    def a_start(self):
        self.events.append("a_start")

    @on_shutdown
    async def stop(self):
        self.events.append("stop")


async def test_lifespan_hooks_run_in_order(make_app):
    app = make_app(app_base=LifecycleApp)
    app.events = []
    async with LifespanManager(app):
        assert app.events == ["a_start", "b_start"]
    assert app.events == ["a_start", "b_start", "stop"]


class FailingStartupApp(Patera):
    @on_startup
    async def boom(self):
        raise RuntimeError("cannot start")


async def test_failing_startup_is_reported(make_app):
    app = make_app(app_base=FailingStartupApp)
    sent: list[dict] = []
    messages = [{"type": "lifespan.startup"}]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    # Returns instead of hanging; the server is told that startup failed.
    await app({"type": "lifespan"}, receive, send)
    assert sent[0]["type"] == "lifespan.startup.failed"
    assert "cannot start" in sent[0]["message"]


ORDER: list[str] = []


@middleware(order=10)
class Outer(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        ORDER.append("outer-in")
        res = await self.next(req)
        ORDER.append("outer-out")
        res.set_header("x-outer", "1")
        return res


@middleware(order=20)
class Inner(MiddlewareBase):
    async def middleware(self, req: Request) -> Response:
        ORDER.append("inner-in")
        if req.headers.get("x-short-circuit"):
            return req.res.text("short").status(418)
        res = await self.next(req)
        ORDER.append("inner-out")
        return res


@path("/mw")
class MwController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        ORDER.append("handler")
        return req.res.text("ok")


async def test_middleware_order_and_short_circuit(make_app, client_for):
    ORDER.clear()
    app = make_app(controllers=[MwController], middleware=[Inner, Outer])
    async with client_for(app) as client:
        res = await client.get("/mw/")
        assert res.headers["x-outer"] == "1"
        assert ORDER == ["outer-in", "inner-in", "handler", "inner-out", "outer-out"]

        ORDER.clear()
        res = await client.get("/mw/", headers={"x-short-circuit": "1"})
        assert res.status_code == 418
        assert ORDER == ["outer-in", "inner-in", "outer-out"]


def test_middleware_order_validation(make_app):
    with pytest.raises(ValueError):
        middleware(order=0)

    class NoOrder(MiddlewareBase):
        _middleware = True

        async def middleware(self, req):  # pragma: no cover
            return await self.next(req)

    app = make_app()
    with pytest.raises(ValueError):
        app.register_middleware(NoOrder)


async def test_middleware_cannot_be_registered_after_build(make_app, client_for):
    app = make_app()
    async with client_for(app):
        pass
    with pytest.raises(RuntimeError):
        app.register_middleware(Outer)


DISCOVERY_FILES = {
    "api/users_api.py": """
        from patera.controller import Controller, path, get

        @path("/discovered")
        class DiscoveredApi(Controller):
            @get("/")
            async def index(self, req):
                return req.res.text("found me")
    """,
    "exceptions/handlers.py": """
        from patera.exceptions import ExceptionHandler, exception_handler, handles

        @exception_handler
        class DiscoveredHandler(ExceptionHandler):
            @handles(KeyError)
            async def key_error(self, req, exc):
                return req.res.text("key error").status(400)
    """,
    "middleware/header_mw.py": """
        from patera.middleware import MiddlewareBase, middleware

        @middleware(order=50)
        class HeaderMiddleware(MiddlewareBase):
            async def middleware(self, req):
                res = await self.next(req)
                res.set_header("x-discovered", "yes")
                return res
    """,
}


async def test_auto_discovery_of_project_modules(make_app, client_for):
    app = make_app(files=DISCOVERY_FILES)
    assert app.get_controller("DiscoveredApi") is not None
    assert KeyError in app._exception_handlers
    async with client_for(app) as client:
        res = await client.get("/discovered/")
        assert res.text == "found me"
        assert res.headers["x-discovered"] == "yes"


@path("/ws")
class SocketController(Controller):
    @socket("/echo/<name>")
    async def echo(self, req: Request, name: str) -> None:
        await req.accept()
        message = await req.receive()
        await req.send(
            {"type": "websocket.send", "text": f"{name}: {message.get('text')}"}
        )
        await req.send({"type": "websocket.close", "code": 1000})


async def test_websocket_routing(make_app):
    app = make_app(controllers=[SocketController])
    app.build()
    sent: list[dict] = []
    incoming = [
        {"type": "websocket.connect"},
        {"type": "websocket.receive", "text": "hi"},
    ]

    async def receive():
        return incoming.pop(0) if incoming else {"type": "websocket.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "websocket",
        "path": "/ws/echo/ana",
        "scheme": "ws",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
    }
    # consume the connect message the way a server would
    await receive()
    await app(scope, receive, send)
    assert sent[0] == {"type": "websocket.accept"}
    assert sent[1] == {"type": "websocket.send", "text": "ana: hi"}

    sent.clear()
    scope["path"] = "/ws/unknown"
    await app(scope, receive, send)
    assert sent[0]["type"] == "websocket.close"
    assert sent[0]["code"] == 1008


async def test_zero_copy_ends_the_body_when_the_file_shrinks(make_app, tmp_path):
    from patera.utilities import file_response

    target = tmp_path / "shrinking.bin"
    target.write_bytes(PNG)
    app = make_app()
    req = make_request(app)
    res = file_response(req.res, str(target), req.headers)
    target.write_bytes(PNG[:100])  # the file shrinks before it is sent

    sent = []

    async def send(message):
        sent.append(message)

    await app.send_response(res, send)
    bodies = [m for m in sent if m["type"] == "http.response.body"]
    assert b"".join(m["body"] for m in bodies) == PNG[:100]
    assert bodies[-1]["more_body"] is False


async def test_shutdown_waits_for_background_tasks(make_app, client_for):
    from patera import run_in_background

    events: list[str] = []

    async def send_report():
        await asyncio.sleep(0.05)
        events.append("report sent")

    app = make_app()
    app.add_on_shutdown_method(lambda: events.append("shutdown method"))
    async with client_for(app):
        run_in_background(send_report)
    # The task finished before the shutdown methods ran
    assert events == ["report sent", "shutdown method"]


async def test_shutdown_cancels_background_tasks_after_the_timeout(
    make_app, client_for
):
    from patera import run_in_background

    async def endless():
        await asyncio.sleep(60)

    app = make_app(
        BACKGROUND_TASKS_SHUTDOWN_TIMEOUT=0.05,
        LOG_FILES={"ENQUEUE": False, "LEVEL": "INFO"},
    )
    async with client_for(app):
        task = run_in_background(endless)
    assert task.cancelled()
    messages = [r["message"] for r in app.log_files.read()]
    assert any("Cancelled 1 background task" in m for m in messages)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("report.pdf", 'attachment; filename="report.pdf"'),
        (
            "poročilo.pdf",
            "attachment; filename=\"poro_ilo.pdf\"; filename*=UTF-8''poro%C4%8Dilo.pdf",
        ),
        ('a"b.pdf', "attachment; filename=\"a_b.pdf\"; filename*=UTF-8''a%22b.pdf"),
    ],
)
async def test_file_response_download_name(
    make_app, client_for, tmp_path, name, expected
):
    from patera.utilities import file_response

    target = tmp_path / "data.bin"
    target.write_bytes(b"0123456789")

    @path("/dl")
    class Downloads(Controller):
        @get("/")
        async def download(self, req: Request) -> Response:
            return file_response(req.res, str(target), req.headers, download_name=name)

    app = make_app(controllers=[Downloads])
    async with client_for(app) as client:
        res = await client.get("/dl/")
    assert res.status_code == 200
    assert res.content == b"0123456789"
    assert res.headers["content-disposition"] == expected


async def test_logging_works_again_after_a_second_startup(make_app, client_for):
    app = make_app()
    async with client_for(app):
        app.logger.info("first run")
    async with client_for(app):
        app.logger.info("second run")
    messages = [record["message"] for record in app.log_files.read()]
    assert "first run" in messages
    assert "second run" in messages
