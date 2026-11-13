"""
Snapshots of the HTTP behaviour the request pipeline produces today.

Every case sends one request straight through the ASGI interface and compares
everything the application sent (status, every header in order, the exact
body bytes) and the request observer's record with a recorded snapshot.

The snapshots lock the behaviour before the request pipeline is reworked
(Part A of the core refactor: routing errors and static resources passing
through the middleware chain). That rework must leave every snapshot as it
is. A snapshot that has to change marks a deliberate behaviour change:
update it by hand, in the same commit as the change, and say why there.

Deliberate changes since the first recording:

- Trailing-slash redirects send a path-only Location with the request's
  query string (``/api/items/?page=2``) instead of ``http:///api/items/``.
- Routing errors (and a missing static page) answer HEAD without a body.
- Routing-error bodies are encoded like other JSON responses: compact, with
  ``charset=utf-8`` in the content type.
- 405 responses list the allowed methods sorted, in the Allow header and in
  ``data.allowed_methods`` (they followed the order of a set before).

To print freshly recorded snapshots for review:

    python -m tests.integration.test_http_snapshots
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from patera import Request, Response
from patera.controller import Controller, get, path, post, socket
from patera.exceptions.http_exceptions import BaseHttpException

from tests.helpers import make_receive, make_scope

pytestmark = pytest.mark.integration

ORIGIN = "https://app.example"
OTHER_ORIGIN = "https://evil.example"
# Static files get ETag and Last-Modified from the file's modification time.
FIXED_MTIME = 1_700_000_000  # 2023-11-14T22:13:20Z


@path("/api")
class Items(Controller):
    @get("/items/")
    async def items(self, req: Request) -> Response:
        return req.res.json([{"id": 1}])

    @post("/items/")
    async def create(self, req: Request) -> Response:
        return req.res.json({"id": 2}).status(201)

    @get("/teapot")
    async def teapot(self, req: Request) -> Response:
        raise BaseHttpException("short and stout", status_code=418)

    @get("/boom")
    async def boom(self, req: Request) -> Response:
        raise RuntimeError("boom")


@path("/ws")
class Sockets(Controller):
    @socket("/echo/<name>")
    async def echo(self, req: Request, name: str) -> None:
        await req.accept()


# Bytes, not text: text files would get CRLF line endings on Windows and
# change the sizes and ETags.
FILES: dict[str, Any] = {
    "static/hello.txt": b"hello\n",
    "pages/about.html": b"<p>About</p>\n",
}

# Application variants: configuration on top of the shared defaults.
VARIANTS: dict[str, dict[str, Any]] = {
    "default": {},
    "strict_slashes": {"STRICT_SLASHES": True},
    "cors_disabled": {"CORS_ENABLED": False},
    "static_pages": {
        "USE_STATIC_PAGES": True,
        "STATIC_PAGES_DIR": "pages",
        "STATIC_PAGES_URL": "/pages",
    },
}


class Case(NamedTuple):
    id: str
    variant: str
    method: str
    path: str
    headers: dict[str, str]
    query_string: bytes = b""


def preflight(method: str) -> dict[str, str]:
    return {"origin": ORIGIN, "access-control-request-method": method}


CASES: list[Case] = [
    # Routing errors: answered before the middleware chain runs.
    Case("not_found", "default", "GET", "/nowhere", {}),
    Case("not_found_allowed_origin", "default", "GET", "/nowhere", {"origin": ORIGIN}),
    Case(
        "not_found_other_origin",
        "default",
        "GET",
        "/nowhere",
        {"origin": OTHER_ORIGIN},
    ),
    Case("not_found_head", "default", "HEAD", "/nowhere", {}),
    Case(
        "not_found_cors_disabled",
        "cors_disabled",
        "GET",
        "/nowhere",
        {"origin": ORIGIN},
    ),
    Case("method_not_allowed", "default", "DELETE", "/api/items/", {}),
    Case(
        "method_not_allowed_allowed_origin",
        "default",
        "DELETE",
        "/api/items/",
        {"origin": ORIGIN},
    ),
    Case("http_request_to_socket_route", "default", "GET", "/ws/echo/ana", {}),
    Case("trailing_slash_missing", "default", "GET", "/api/items", {}),
    Case("redirect_strict_slashes", "strict_slashes", "GET", "/api/items", {}),
    Case(
        "redirect_strict_slashes_allowed_origin",
        "strict_slashes",
        "GET",
        "/api/items",
        {"origin": ORIGIN},
    ),
    Case("redirect_strict_slashes_post", "strict_slashes", "POST", "/api/items", {}),
    Case("redirect_strict_slashes_head", "strict_slashes", "HEAD", "/api/items", {}),
    Case(
        "redirect_strict_slashes_query",
        "strict_slashes",
        "GET",
        "/api/items",
        {},
        b"page=2&q=caf%C3%A9",
    ),
    # OPTIONS and CORS preflights.
    Case("preflight_unknown_path", "default", "OPTIONS", "/nowhere", preflight("GET")),
    Case("options_unknown_path", "default", "OPTIONS", "/nowhere", {}),
    Case(
        "preflight_unknown_path_cors_disabled",
        "cors_disabled",
        "OPTIONS",
        "/nowhere",
        preflight("GET"),
    ),
    Case(
        "preflight_known_route", "default", "OPTIONS", "/api/items/", preflight("POST")
    ),
    # PATCH is allowed by CORS_ALLOW_METHODS, though the route has no PATCH.
    Case(
        "preflight_method_not_on_route",
        "default",
        "OPTIONS",
        "/api/items/",
        preflight("PATCH"),
    ),
    Case(
        "preflight_other_origin",
        "default",
        "OPTIONS",
        "/api/items/",
        {"origin": OTHER_ORIGIN, "access-control-request-method": "POST"},
    ),
    Case("automatic_options", "default", "OPTIONS", "/api/items/", {}),
    # Routed requests.
    Case("ok_json", "default", "GET", "/api/items/", {}),
    Case("ok_json_allowed_origin", "default", "GET", "/api/items/", {"origin": ORIGIN}),
    Case("ok_json_head", "default", "HEAD", "/api/items/", {}),
    Case("created", "default", "POST", "/api/items/", {"origin": ORIGIN}),
    Case("handled_exception", "default", "GET", "/api/teapot", {"origin": ORIGIN}),
    Case("unhandled_exception", "default", "GET", "/api/boom", {"origin": ORIGIN}),
    # Static resources: handled beside the middleware chain.
    Case("static_file", "default", "GET", "/static/hello.txt", {}),
    Case(
        "static_file_allowed_origin",
        "default",
        "GET",
        "/static/hello.txt",
        {"origin": ORIGIN},
    ),
    Case("static_file_head", "default", "HEAD", "/static/hello.txt", {}),
    Case(
        "static_file_range",
        "default",
        "GET",
        "/static/hello.txt",
        {"range": "bytes=0-2"},
    ),
    Case(
        "static_file_missing",
        "default",
        "GET",
        "/static/missing.txt",
        {"origin": ORIGIN},
    ),
    Case("static_page", "static_pages", "GET", "/pages/about", {"origin": ORIGIN}),
    Case("static_page_missing", "static_pages", "GET", "/pages/missing", {}),
    Case("static_page_missing_head", "static_pages", "HEAD", "/pages/missing", {}),
]


def build_app(make_app: Any, variant: str) -> tuple[Any, list[Any]]:
    """Builds the variant's application and attaches a recording observer."""
    app = make_app(
        controllers=[Items, Sockets],
        files=FILES,
        CORS_ALLOW_ORIGINS=[ORIGIN],
        DEBUG=False,
        **VARIANTS[variant],
    )
    root = Path(app.root_path)
    for name in FILES:
        os.utime(root / name, (FIXED_MTIME, FIXED_MTIME))
    records: list[Any] = []
    app.add_request_observer(records.append)
    return app, records


async def exchange(app: Any, records: list[Any], case: Case) -> dict[str, Any]:
    """Sends the case's request and returns everything that came back."""
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    raised = None
    try:
        await app(
            make_scope(
                case.method,
                case.path,
                query_string=case.query_string,
                headers=case.headers,
            ),
            make_receive(),
            send,
        )
    except Exception as exc:  # recorded: an escaping exception is behaviour too
        raised = repr(exc)

    record = records[-1] if records else None
    return {
        "messages": sent,
        "raised": raised,
        "record": None
        if record is None
        else (record.method, record.path, record.route, record.status_code),
    }


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
async def test_http_snapshot(make_app, case: Case):
    app, records = build_app(make_app, case.variant)
    assert await exchange(app, records, case) == SNAPSHOTS[case.id]


async def test_bad_request_snapshot(make_app):
    # 400 for an HTTP request matching a WebSocket rule (WebsocketMismatch).
    # Patera keeps WebSocket routes in their own router, so a request cannot
    # reach this path; the helper's output is pinned directly.
    app, _ = build_app(make_app, "default")
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app.abort_bad_request(send)
    assert sent == BAD_REQUEST_SNAPSHOT


def test_every_case_has_a_snapshot():
    assert {case.id for case in CASES} == set(SNAPSHOTS)


def record_snapshots() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Runs every case against the current code; used to (re)write snapshots."""
    import tempfile

    from tests.helpers import AppFactory

    async def run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        factory = AppFactory(Path(tempfile.mkdtemp()))
        try:
            snapshots = {}
            for case in CASES:
                app, records = build_app(factory, case.variant)
                snapshots[case.id] = await exchange(app, records, case)
            app, _ = build_app(factory, "default")
            sent: list[dict[str, Any]] = []

            async def send(message: dict[str, Any]) -> None:
                sent.append(message)

            await app.abort_bad_request(send)
            return snapshots, sent
        finally:
            factory.cleanup()

    return asyncio.run(run())


if __name__ == "__main__":
    import pprint

    recorded, bad_request = record_snapshots()
    print("SNAPSHOTS = ", end="")
    pprint.pprint(recorded, width=88, sort_dicts=False)
    print("\nBAD_REQUEST_SNAPSHOT = ", end="")
    pprint.pprint(bad_request, width=88, sort_dicts=False)


# ---- Recorded snapshots --------------------------------------------------------
# Recorded from the code before the request-pipeline rework.

SNAPSHOTS: dict[str, Any] = {
    "not_found": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("GET", "/nowhere", None, 404),
    },
    "not_found_allowed_origin": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("GET", "/nowhere", None, 404),
    },
    "not_found_other_origin": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("GET", "/nowhere", None, 404),
    },
    "not_found_head": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b""},
        ],
        "raised": None,
        "record": ("HEAD", "/nowhere", None, 404),
    },
    "not_found_cors_disabled": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("GET", "/nowhere", None, 404),
    },
    "method_not_allowed": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 405,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"98"),
                    (b"allow", b"GET, HEAD, POST"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Method not allowed","data":{"allowed_methods":["GET","HEAD","POST"]}}',
            },
        ],
        "raised": None,
        "record": ("DELETE", "/api/items/", None, 405),
    },
    "method_not_allowed_allowed_origin": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 405,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"98"),
                    (b"allow", b"GET, HEAD, POST"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Method not allowed","data":{"allowed_methods":["GET","HEAD","POST"]}}',
            },
        ],
        "raised": None,
        "record": ("DELETE", "/api/items/", None, 405),
    },
    "http_request_to_socket_route": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("GET", "/ws/echo/ana", None, 404),
    },
    "trailing_slash_missing": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"10"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b'[{"id":1}]', "more_body": False},
        ],
        "raised": None,
        "record": ("GET", "/api/items", "/api/items/", 200),
    },
    "redirect_strict_slashes": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [
                    (b"location", b"/api/items/"),
                    (b"content-length", b"0"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b""},
        ],
        "raised": None,
        "record": ("GET", "/api/items", None, 308),
    },
    "redirect_strict_slashes_allowed_origin": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [
                    (b"location", b"/api/items/"),
                    (b"content-length", b"0"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b""},
        ],
        "raised": None,
        "record": ("GET", "/api/items", None, 308),
    },
    "redirect_strict_slashes_post": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [
                    (b"location", b"/api/items/"),
                    (b"content-length", b"0"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b""},
        ],
        "raised": None,
        "record": ("POST", "/api/items", None, 308),
    },
    "redirect_strict_slashes_head": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [
                    (b"location", b"/api/items/"),
                    (b"content-length", b"0"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b""},
        ],
        "raised": None,
        "record": ("HEAD", "/api/items", None, 308),
    },
    "redirect_strict_slashes_query": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 308,
                "headers": [
                    (b"location", b"/api/items/?page=2&q=caf%C3%A9"),
                    (b"content-length", b"0"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b""},
        ],
        "raised": None,
        "record": ("GET", "/api/items", None, 308),
    },
    "preflight_unknown_path": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("OPTIONS", "/nowhere", None, 404),
    },
    "options_unknown_path": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("OPTIONS", "/nowhere", None, 404),
    },
    "preflight_unknown_path_cors_disabled": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("OPTIONS", "/nowhere", None, 404),
    },
    "preflight_known_route": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-origin", b"https://app.example"),
                    (
                        b"access-control-allow-methods",
                        b"GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    ),
                    (b"access-control-allow-headers", b"Authorization, Content-Type"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b"", "more_body": False},
        ],
        "raised": None,
        "record": ("OPTIONS", "/api/items/", "/api/items/", 204),
    },
    "preflight_method_not_on_route": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"access-control-allow-origin", b"https://app.example"),
                    (
                        b"access-control-allow-methods",
                        b"GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    ),
                    (b"access-control-allow-headers", b"Authorization, Content-Type"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b"", "more_body": False},
        ],
        "raised": None,
        "record": ("OPTIONS", "/api/items/", "/api/items/", 204),
    },
    "preflight_other_origin": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"54"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"CORS origin not allowed"}',
                "more_body": False,
            },
        ],
        "raised": None,
        "record": ("OPTIONS", "/api/items/", "/api/items/", 403),
    },
    "automatic_options": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [
                    (b"allow", b"GET, HEAD, OPTIONS, POST"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b"", "more_body": False},
        ],
        "raised": None,
        "record": ("OPTIONS", "/api/items/", "/api/items/", 204),
    },
    "ok_json": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"10"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b'[{"id":1}]', "more_body": False},
        ],
        "raised": None,
        "record": ("GET", "/api/items/", "/api/items/", 200),
    },
    "ok_json_allowed_origin": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"10"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b'[{"id":1}]', "more_body": False},
        ],
        "raised": None,
        "record": ("GET", "/api/items/", "/api/items/", 200),
    },
    "ok_json_head": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"10"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b"", "more_body": False},
        ],
        "raised": None,
        "record": ("HEAD", "/api/items/", "/api/items/", 200),
    },
    "created": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 201,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"8"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b'{"id":2}', "more_body": False},
        ],
        "raised": None,
        "record": ("POST", "/api/items/", "/api/items/", 201),
    },
    "handled_exception": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 418,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"58"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"short and stout","data":null}',
                "more_body": False,
            },
        ],
        "raised": None,
        "record": ("GET", "/api/teapot", "/api/teapot", 418),
    },
    "unhandled_exception": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"52"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Internal server error"}',
                "more_body": False,
            },
        ],
        "raised": None,
        "record": ("GET", "/api/boom", "/api/boom", 500),
    },
    "static_file": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"accept-ranges", b"bytes"),
                    (b"etag", b'"17979cfe362a0000-6"'),
                    (b"last-modified", b"Tue, 14 Nov 2023 22:13:20 GMT"),
                    (b"cache-control", b"public, max-age=300"),
                    (b"content-length", b"6"),
                ],
            },
            {"type": "http.response.body", "body": b"hello\n", "more_body": False},
        ],
        "raised": None,
        "record": ("GET", "/static/hello.txt", "/static/<path:filename>", 200),
    },
    "static_file_allowed_origin": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"accept-ranges", b"bytes"),
                    (b"etag", b'"17979cfe362a0000-6"'),
                    (b"last-modified", b"Tue, 14 Nov 2023 22:13:20 GMT"),
                    (b"cache-control", b"public, max-age=300"),
                    (b"content-length", b"6"),
                ],
            },
            {"type": "http.response.body", "body": b"hello\n", "more_body": False},
        ],
        "raised": None,
        "record": ("GET", "/static/hello.txt", "/static/<path:filename>", 200),
    },
    "static_file_head": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"accept-ranges", b"bytes"),
                    (b"etag", b'"17979cfe362a0000-6"'),
                    (b"last-modified", b"Tue, 14 Nov 2023 22:13:20 GMT"),
                    (b"cache-control", b"public, max-age=300"),
                    (b"content-length", b"6"),
                ],
            },
            {"type": "http.response.body", "body": b"", "more_body": False},
        ],
        "raised": None,
        "record": ("HEAD", "/static/hello.txt", "/static/<path:filename>", 200),
    },
    "static_file_range": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 206,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"accept-ranges", b"bytes"),
                    (b"etag", b'"17979cfe362a0000-6"'),
                    (b"last-modified", b"Tue, 14 Nov 2023 22:13:20 GMT"),
                    (b"cache-control", b"public, max-age=300"),
                    (b"content-range", b"bytes 0-2/6"),
                    (b"content-length", b"3"),
                ],
            },
            {"type": "http.response.body", "body": b"hel", "more_body": False},
        ],
        "raised": None,
        "record": ("GET", "/static/hello.txt", "/static/<path:filename>", 206),
    },
    "static_file_missing": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"65"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Static asset not found","data":null}',
                "more_body": False,
            },
        ],
        "raised": None,
        "record": ("GET", "/static/missing.txt", "/static/<path:filename>", 404),
    },
    "static_page": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", b"12"),
                    (b"access-control-allow-origin", b"https://app.example"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b"<p>About</p>", "more_body": False},
        ],
        "raised": None,
        "record": ("GET", "/pages/about", "/pages/<path:page>", 200),
    },
    "static_page_missing": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"vary", b"Origin"),
                ],
            },
            {
                "type": "http.response.body",
                "body": b'{"status":"error","message":"Endpoint not found"}',
            },
        ],
        "raised": None,
        "record": ("GET", "/pages/missing", "/pages/<path:page>", 404),
    },
    "static_page_missing_head": {
        "messages": [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", b"49"),
                    (b"vary", b"Origin"),
                ],
            },
            {"type": "http.response.body", "body": b""},
        ],
        "raised": None,
        "record": ("HEAD", "/pages/missing", "/pages/<path:page>", 404),
    },
}

BAD_REQUEST_SNAPSHOT: list[dict[str, Any]] = [
    {
        "type": "http.response.start",
        "status": 400,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", b"42"),
        ],
    },
    {
        "type": "http.response.body",
        "body": b'{"status":"error","message":"Bad request"}',
    },
]
