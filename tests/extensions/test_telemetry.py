"""
patera-telemetry: request spans, the duration metric, log correlation,
privacy options, propagation, integrations and SDK setup.

OpenTelemetry's global providers can be set once per process, so this module
installs in-memory providers once; the SETUP_SDK tests run in a subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from loguru import logger
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from patera import Request, Response
from patera.controller import Controller, get, path
from patera.exceptions.http_exceptions import BaseHttpException
from patera.telemetry import (
    Telemetry,
    TelemetryMiddleware,
    run_traced_in_background,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

# ---- In-memory providers, installed once per process ----------------------------

_EXPORTER = InMemorySpanExporter()
_READER = InMemoryMetricReader()
_tracer_provider = TracerProvider()
_tracer_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_tracer_provider)
metrics.set_meter_provider(MeterProvider(metric_readers=[_READER]))
_INSTALLED = trace.get_tracer_provider() is _tracer_provider


@pytest.fixture
def spans():
    if not _INSTALLED:  # pragma: no cover - another module set providers first
        pytest.skip("global OpenTelemetry providers were set elsewhere")
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


def server_spans(exporter):
    return [s for s in exporter.get_finished_spans() if s.kind == SpanKind.SERVER]


# ---- Application -------------------------------------------------------------------


@path("/api")
class Items(Controller):
    @get("/items/")
    async def items(self, req: Request) -> Response:
        return req.res.json([])

    @get("/teapot")
    async def teapot(self, req: Request) -> Response:
        raise BaseHttpException("short and stout", status_code=418)

    @get("/boom")
    async def boom(self, req: Request) -> Response:
        raise RuntimeError("boom")

    @get("/stream")
    async def stream(self, req: Request) -> Response:
        async def chunks():
            with trace.get_tracer("test").start_as_current_span("produce chunk"):
                yield b"chunk"

        return req.res.stream(chunks())

    @get("/logs")
    async def logs(self, req: Request) -> Response:
        logger.info("inside the request")
        return req.res.json({})

    @get("/me")
    async def me(self, req: Request) -> Response:
        req.set_user(type("User", (), {"id": 42})())
        return req.res.json({})

    @get("/background")
    async def background(self, req: Request) -> Response:
        run_traced_in_background("send report", lambda: None)
        return req.res.json({})

    @get("/health")
    async def health(self, req: Request) -> Response:
        return req.res.json({"ok": True})


FILES = {"static/hello.txt": b"hello\n"}


def make(make_app, **telemetry: Any):
    return make_app(
        controllers=[Items],
        extensions=[Telemetry],
        files=FILES,
        DEBUG=False,
        TELEMETRY=telemetry,
    )


async def fetch(app, client_for, url: str, **kwargs: Any):
    async with client_for(app) as client:
        return await client.get(url, **kwargs)


# ---- Spans --------------------------------------------------------------------------


async def test_a_request_becomes_a_server_span(make_app, client_for, spans):
    res = await fetch(make(make_app), client_for, "/api/items/")
    assert res.status_code == 200
    (span,) = server_spans(spans)
    assert span.name == "GET /api/items/"
    assert span.status.status_code == StatusCode.UNSET
    attrs = dict(span.attributes)
    assert attrs["http.request.method"] == "GET"
    assert attrs["http.route"] == "/api/items/"
    assert attrs["url.path"] == "/api/items/"
    assert attrs["url.scheme"] == "http"
    assert attrs["http.response.status_code"] == 200
    assert attrs["server.address"] == "testserver"
    assert attrs["code.function.name"].endswith("Items.items")
    # Privacy defaults: no client address, query or headers.
    assert "client.address" not in attrs
    assert "url.query" not in attrs
    assert not [k for k in attrs if k.startswith("http.request.header.")]
    # The response is unchanged by default.
    assert "x-trace-id" not in res.headers


@pytest.mark.parametrize(
    ("method", "url", "name", "status"),
    [
        ("GET", "/nowhere", "GET", 404),
        ("DELETE", "/api/items/", "DELETE", 405),
        ("GET", "/api/teapot", "GET /api/teapot", 418),
    ],
)
async def test_client_errors_are_not_span_errors(
    make_app, client_for, spans, method, url, name, status
):
    async with client_for(make(make_app)) as client:
        assert (await client.request(method, url)).status_code == status
    (span,) = server_spans(spans)
    assert span.name == name
    assert span.attributes["http.response.status_code"] == status
    assert span.status.status_code == StatusCode.UNSET
    assert ("http.route" in span.attributes) == (status == 418)


async def test_an_unhandled_exception_marks_the_span(make_app, client_for, spans):
    assert (await fetch(make(make_app), client_for, "/api/boom")).status_code == 500
    (span,) = server_spans(spans)
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    assert span.attributes["http.response.status_code"] == 500
    assert [e.name for e in span.events] == ["exception"]


async def test_spans_during_a_streamed_body_are_children(make_app, client_for, spans):
    assert (await fetch(make(make_app), client_for, "/api/stream")).content == b"chunk"
    (server,) = server_spans(spans)
    (child,) = [s for s in spans.get_finished_spans() if s.name == "produce chunk"]
    assert child.parent.span_id == server.context.span_id
    # The request span ends after the body: it covers the child.
    assert server.end_time >= child.end_time


TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


async def test_an_incoming_trace_is_continued(make_app, client_for, spans):
    await fetch(
        make(make_app), client_for, "/api/items/", headers={"traceparent": TRACEPARENT}
    )
    (span,) = server_spans(spans)
    assert format(span.context.trace_id, "032x") == "0af7651916cd43dd8448eb211c80319c"
    assert format(span.parent.span_id, "016x") == "b7ad6b7169203331"


async def test_an_untrusted_incoming_trace_is_only_linked(make_app, client_for, spans):
    app = make(make_app, TRUST_INCOMING_CONTEXT=False)
    await fetch(app, client_for, "/api/items/", headers={"traceparent": TRACEPARENT})
    (span,) = server_spans(spans)
    assert span.parent is None
    assert format(span.context.trace_id, "032x") != "0af7651916cd43dd8448eb211c80319c"
    (link,) = span.links
    assert format(link.context.trace_id, "032x") == "0af7651916cd43dd8448eb211c80319c"


# ---- Which requests are traced ----------------------------------------------------------


async def test_static_files_are_not_traced_by_default(make_app, client_for, spans):
    assert (
        await fetch(make(make_app), client_for, "/static/hello.txt")
    ).status_code == 200
    assert server_spans(spans) == []


async def test_static_files_can_be_traced(make_app, client_for, spans):
    await fetch(make(make_app, TRACE_STATIC=True), client_for, "/static/hello.txt")
    (span,) = server_spans(spans)
    assert span.name == "GET /static/<path:filename>"


async def test_unmatched_requests_can_be_skipped(make_app, client_for, spans):
    await fetch(make(make_app, TRACE_UNMATCHED=False), client_for, "/nowhere")
    assert server_spans(spans) == []


async def test_excluded_paths_are_not_traced(make_app, client_for, spans):
    app = make(make_app, EXCLUDE_PATHS=["/api/health", "/api/item*"])
    async with client_for(app) as client:
        await client.get("/api/health")
        await client.get("/api/items/")
        await client.get("/api/teapot")
    assert [s.name for s in server_spans(spans)] == ["GET /api/teapot"]


async def test_disabled_extension_registers_nothing(make_app, client_for, spans):
    app = make(make_app, ENABLED=False)
    assert TelemetryMiddleware not in app._middleware_classes.values()
    await fetch(app, client_for, "/api/items/")
    assert server_spans(spans) == []


def test_the_middleware_needs_the_extension(make_app):
    app = make_app(middleware=[TelemetryMiddleware])
    with pytest.raises(RuntimeError, match="registered by the Telemetry extension"):
        app.build()


# ---- What is recorded ------------------------------------------------------------------


async def test_opt_in_attributes(make_app, client_for, spans):
    app = make(
        make_app,
        RECORD_CLIENT_ADDRESS=True,
        RECORD_QUERY=True,
        CAPTURE_REQUEST_HEADERS=["X-Request-Id", "Authorization"],
        CAPTURE_RESPONSE_HEADERS=["content-type"],
    )
    await fetch(
        app,
        client_for,
        "/api/items/?page=2",
        headers={"x-request-id": "abc", "authorization": "Bearer secret"},
    )
    attrs = dict(server_spans(spans)[0].attributes)
    assert attrs["url.query"] == "page=2"
    assert attrs["client.address"] == "127.0.0.1"
    assert attrs["http.request.header.x-request-id"] == ("abc",)
    assert attrs["http.request.header.authorization"] == ("[REDACTED]",)
    assert attrs["http.response.header.content-type"] == (
        "application/json; charset=utf-8",
    )


async def test_user_id_is_opt_in(make_app, client_for, spans):
    await fetch(make(make_app), client_for, "/api/me")
    assert "enduser.id" not in server_spans(spans)[0].attributes
    spans.clear()
    await fetch(make(make_app, RECORD_USER_ID=True), client_for, "/api/me")
    assert server_spans(spans)[0].attributes["enduser.id"] == "42"


async def test_trace_id_response_header(make_app, client_for, spans):
    res = await fetch(
        make(make_app, TRACE_ID_RESPONSE_HEADER="X-Trace-Id"), client_for, "/api/items/"
    )
    (span,) = server_spans(spans)
    assert res.headers["x-trace-id"] == format(span.context.trace_id, "032x")


# ---- Logs, metrics and background work -----------------------------------------------


async def test_log_records_carry_the_trace(make_app, client_for, spans):
    records: list[dict] = []
    sink = logger.add(lambda message: records.append(message.record), level="INFO")
    try:
        await fetch(make(make_app), client_for, "/api/logs")
        logger.info("outside any request")
    finally:
        logger.remove(sink)
    (span,) = server_spans(spans)
    inside = next(r for r in records if r["message"] == "inside the request")
    outside = next(r for r in records if r["message"] == "outside any request")
    assert inside["extra"]["trace_id"] == format(span.context.trace_id, "032x")
    assert inside["extra"]["span_id"] == format(span.context.span_id, "016x")
    assert "trace_id" not in outside["extra"]


async def test_log_correlation_can_be_turned_off(make_app, client_for, spans):
    records: list[dict] = []
    sink = logger.add(lambda message: records.append(message.record), level="INFO")
    try:
        await fetch(make(make_app, LOG_CORRELATION=False), client_for, "/api/logs")
    finally:
        logger.remove(sink)
    inside = next(r for r in records if r["message"] == "inside the request")
    assert "trace_id" not in inside["extra"]


def duration_points():
    data = _READER.get_metrics_data()
    points = []
    for resource_metrics in data.resource_metrics if data else []:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "http.server.request.duration":
                    assert metric.unit == "s"
                    points.extend(metric.data.data_points)
    return points


async def test_request_duration_metric(make_app, client_for, spans):
    app = make(make_app)
    async with client_for(app) as client:
        await client.get("/api/health")
        await client.get("/no/such/metric/path")
    points = {tuple(sorted(p.attributes.items())): p for p in duration_points()}
    health = (
        ("http.request.method", "GET"),
        ("http.response.status_code", 200),
        ("http.route", "/api/health"),
        ("url.scheme", "http"),
    )
    assert health in points and points[health].count >= 1
    # Unmatched requests have no route: one bounded series, not one per path.
    for attributes in points:
        assert ("url.path", "/no/such/metric/path") not in attributes


async def test_background_work_gets_its_own_linked_trace(make_app, client_for, spans):
    await fetch(make(make_app), client_for, "/api/background")
    (server,) = server_spans(spans)
    (job,) = [s for s in spans.get_finished_spans() if s.name == "send report"]
    assert job.parent is None
    assert job.context.trace_id != server.context.trace_id
    assert job.links[0].context.span_id == server.context.span_id


# ---- Integrations ------------------------------------------------------------------------


def test_missing_integration_names_its_extra(make_app, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_redis_instrumentation(name, *args, **kwargs):
        if name.startswith("opentelemetry.instrumentation.redis"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_redis_instrumentation)
    with pytest.raises(RuntimeError, match=r"patera-telemetry\[redis\]"):
        make(make_app, INSTRUMENT=["redis"])


async def test_sqlalchemy_queries_become_child_spans(
    make_app, client_for, spans, tmp_path
):
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from sqlalchemy import text

    from patera.database.sql import SqlDatabase, SqlDatabaseManager

    class MainDb(SqlDatabase):
        __db_name__ = "main"

    class Databases(SqlDatabaseManager):
        databases = [MainDb]

    @path("/db")
    class Queries(Controller):
        @get("/one")
        async def one(self, req: Request) -> Response:
            db = self.app.get_extension(Databases)["main"]
            async with db.engine.connect() as conn:
                value = (await conn.execute(text("SELECT 1"))).scalar()
            return req.res.json({"value": value})

    try:
        app = make_app(
            controllers=[Queries],
            # Telemetry first: it instruments before the engine is created.
            extensions=[Telemetry, Databases],
            TELEMETRY={"INSTRUMENT": ["sqlalchemy"]},
            MAIN_DB={"DATABASE_URI": f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}"},
        )
        assert (await fetch(app, client_for, "/db/one")).json() == {"value": 1}
    finally:
        SQLAlchemyInstrumentor().uninstrument()
    (server,) = server_spans(spans)
    queries = [s for s in spans.get_finished_spans() if s.name.startswith("SELECT")]
    assert queries and all(
        q.context.trace_id == server.context.trace_id for q in queries
    )


# ---- SETUP_SDK (subprocess: the global providers can be set once) ------------------------

SDK_SCRIPT = """
import asyncio, json, sys, tempfile
from pathlib import Path
from opentelemetry import trace, metrics
from tests.helpers import AppFactory
from patera.telemetry import Telemetry
from patera.testing import PateraTestClient
{preset}

async def main():
    factory = AppFactory(Path(tempfile.mkdtemp()))
    app = factory(
        extensions=[Telemetry],
        TELEMETRY={{"SETUP_SDK": True, "EXPORTER": "console", "SERVICE_NAME": "svc",
                   "ENVIRONMENT": "test", "METRIC_EXPORT_INTERVAL": 3600}},
    )
    async with PateraTestClient(app) as client:
        await client.get("/nowhere")
        provider = trace.get_tracer_provider()
        print("PROVIDER", type(provider).__module__, flush=True)
        print("KEPT", provider is globals().get("existing"), flush=True)
    telemetry = app.get_extension(Telemetry)
    print("STOPPED", telemetry._providers == (None, None), flush=True)
    factory.cleanup()

asyncio.run(main())
"""


def run_sdk_script(preset: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", SDK_SCRIPT.format(preset=textwrap.dedent(preset))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def console_json(stdout: str) -> list[dict]:
    """The JSON documents the console exporters printed (one per span/batch)."""
    documents, block = [], []
    for line in stdout.splitlines():
        if line == "{":
            block = [line]
        elif block:
            block.append(line)
            if line == "}":
                documents.append(json.loads("\n".join(block)))
                block = []
    return documents


def test_setup_sdk_installs_and_flushes_providers():
    result = run_sdk_script()
    assert result.returncode == 0, result.stderr
    assert "PROVIDER opentelemetry.sdk.trace" in result.stdout
    assert "STOPPED True" in result.stdout
    # The console exporter printed the span when shutdown flushed it.
    (span,) = [block for block in console_json(result.stdout) if "context" in block]
    assert span["name"] == "GET"
    assert span["resource"]["attributes"]["service.name"] == "svc"
    assert span["resource"]["attributes"]["deployment.environment.name"] == "test"


def test_setup_sdk_keeps_providers_configured_elsewhere():
    result = run_sdk_script(
        """
        from opentelemetry.sdk.trace import TracerProvider
        existing = TracerProvider()
        trace.set_tracer_provider(existing)
        """
    )
    assert result.returncode == 0, result.stderr
    assert "KEPT True" in result.stdout
    assert "STOPPED True" in result.stdout
