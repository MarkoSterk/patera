"""
Runs the example application shipped in examples/basic_app.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from patera.testing import PateraTestClient

pytestmark = pytest.mark.integration

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "basic_app"


@pytest.fixture
def example_app(monkeypatch, tmp_path):
    # Keep the example's JSON Lines log file out of the source tree.
    monkeypatch.setenv("PATERA_LOG_FILES__PATH", str(tmp_path / "logs" / "app.jsonl"))
    monkeypatch.syspath_prepend(str(EXAMPLE_DIR))
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, name)
    from app import App  # type: ignore[import-not-found]

    application = App()
    yield application
    application._remove_logger_sinks()
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]


async def test_example_app(example_app):
    async with PateraTestClient(example_app) as client:
        res = await client.get("/api/v1/hello")
        assert res.json() == {"message": "Hello, World!"}

        res = await client.get("/")
        assert res.status_code == 200
        assert "Basic App" in res.text
        assert "1.0.0" in res.text

        assert (await client.get("/pages/hello_world")).status_code == 200
        assert (await client.get("/pages/test/test")).status_code == 200
        assert (await client.get("/static/patera_logo.png")).headers[
            "content-type"
        ] == "image/png"
        assert (await client.get("/openapi/specs.json")).json()["info"][
            "title"
        ] == "Basic App"
