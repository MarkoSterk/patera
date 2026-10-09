from __future__ import annotations

import pytest
from pydantic import BaseModel

from patera.ctx import (
    bind_context_value,
    bind_session,
    current_request,
    get_request_context,
    has_request_context,
    request_context,
)


def test_no_context_outside_requests():
    assert not has_request_context()
    with pytest.raises(RuntimeError):
        current_request.app
    with pytest.raises(RuntimeError):
        get_request_context()


def test_request_context_values():
    with request_context(app="APP", request="REQ", controller="CTRL"):
        assert has_request_context()
        assert current_request.app == "APP"
        assert current_request.req == "REQ"
        assert current_request.controller == "CTRL"
        current_request.user = "ana"
        current_request.roles = ["admin"]
        current_request.set("k", 1)
        assert current_request.user == "ana"
        assert current_request.roles == ["admin"]
        assert current_request.get("k") == 1
        assert current_request.get("missing", 2) == 2
        with bind_context_value("user", "bob"):
            assert current_request.user == "bob"
        assert current_request.user == "ana"
    assert not has_request_context()


def test_bind_session_restores_and_cleans_up():
    with request_context(app="APP"):
        ctx = get_request_context()
        assert current_request.session("main") is None
        with bind_session("main", "S1"):
            assert current_request.session("main") == "S1"
            with bind_session("main", "S2"):
                assert current_request.session("main") == "S2"
            assert current_request.session("main") == "S1"
        # The empty session container is removed again.
        assert ctx.sessions is None


class Nested(BaseModel):
    URI: str = "sqlite://"


def test_get_conf_nested_and_defaults(make_app):
    app = make_app(
        DB=Nested(URI="postgres://x"),
        PLAIN={"INNER": {"VALUE": 5}},
        NONE_VALUE=None,
    )
    assert app.get_conf("DB.URI") == "postgres://x"
    assert app.get_conf("PLAIN.INNER.VALUE") == 5
    assert app.get_conf("PLAIN.INNER.MISSING", "d") == "d"
    assert app.get_conf("MISSING.ANYTHING", "d") == "d"
    assert app.get_conf("NONE_VALUE", "d") == "d"
    assert app.get_conf("APP_NAME") == "Test app"


def test_env_variables_override_configs(make_app, monkeypatch):
    monkeypatch.setenv("PATERA_PORT", "8123")
    monkeypatch.setenv("PATERA_DEBUG", "false")
    app = make_app()
    assert app.configs.PORT == 8123
    assert app.configs.DEBUG is False


def test_value_to_bool():
    from patera import BaseConfig

    assert BaseConfig.value_to_bool("true")
    assert BaseConfig.value_to_bool(1)
    assert not BaseConfig.value_to_bool("no")


def test_version_is_installed_package_version():
    import importlib.metadata

    from patera.patera import PATERA_VERSION

    assert PATERA_VERSION == importlib.metadata.version("patera")
