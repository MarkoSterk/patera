"""
The Patera application object is built from parts (patera._app). These tests
pin down what applications rely on: every method and attribute is still on
Patera, and a subclass that overrides a method is honoured by the parts.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from patera import Patera, Request, Response
from patera._app.snapshot import (
    REGISTRATION_COLLECTIONS,
    restore_registrations,
    snapshot_registrations,
)
from patera.controller import Controller, get, path
from patera.exceptions.http_exceptions import BaseHttpException

# Methods Patera had before it was split into parts. Applications and
# extensions may call or override any of them. (_routing_error_send was
# removed later, deliberately: routing errors now pass through the
# middleware chain, where CORS adds its headers itself.)
PATERA_METHODS = [
    "_load_controllers_exc_handlers_middleware",
    "_unique_list",
    "_load_detected_modules_once",
    "_load_detected_module",
    "_enable_cors",
    "_marked_methods",
    "_get_startup_methods",
    "_get_shutdown_methods",
    "get_conf",
    "_get_nested_config",
    "_get_config_member",
    "_base_app",
    "_send_error",
    "abort_route_not_found",
    "abort_method_not_allowed",
    "abort_bad_request",
    "redirect_request",
    "_iterate_stream",
    "_normalize_chunk",
    "send_response",
    "_lifespan_app",
    "_finish_background_tasks",
    "_attach_logger_sinks",
    "_remove_logger_sinks",
    "add_request_observer",
    "_handle_http_request",
    "_notify_request_observers",
    "_dispatch_http_request",
    "_send_exception_response",
    "_close_context_sessions",
    "_match_automatic_options",
    "_find_exception_handler",
    "default_exception_response",
    "_log_request",
    "_log_response",
    "register_static_controller",
    "register_static_pages_controller",
    "register_openapi_controller",
    "register_middleware",
    "build",
    "add_extension",
    "get_extension",
    "_add_route_function",
    "register_controller",
    "_check_socket_handler",
    "get_controller",
    "register_cli_controller",
    "register_exception_handler",
    "url_for",
    "build_openapi_spec",
    "add_on_startup_method",
    "add_on_shutdown_method",
    "register_alias",
    "cli_commands",
    "print_cli_commands",
    "run_cli",
    "add_template_path",
    "add_template_prefix",
    "_register_app_extensions",
    "flash_message",
    "__call__",
    "_handle_websocket_request",
]

PATERA_ATTRIBUTES = [
    "_router",
    "_socket_router",
    "_app",
    "_is_built",
    "_cors_middleware",
    "_json_spec",
    "_loggers",
    "_logger_sink_ids",
    "_registered_loggers",
    *REGISTRATION_COLLECTIONS,
]


@path("/items")
class Items(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.json({"items": []})

    @get("/teapot")
    async def teapot(self, req: Request) -> Response:
        raise BaseHttpException("short and stout", status_code=418)

    @get("/boom")
    async def boom(self, req: Request) -> Response:
        raise RuntimeError("boom")


@pytest.mark.parametrize("name", PATERA_METHODS)
def test_every_method_is_still_on_patera(name):
    assert callable(getattr(Patera, name))


def test_every_attribute_is_still_on_the_app(make_app):
    app = make_app()
    for name in PATERA_ATTRIBUTES:
        assert hasattr(app, name), name


def test_snapshot_covers_every_registration_collection(make_app):
    app = make_app()
    for name in REGISTRATION_COLLECTIONS:
        assert isinstance(getattr(app, name), (dict, list)), name
    snapshot = snapshot_registrations(app)
    assert set(snapshot.collections) == set(REGISTRATION_COLLECTIONS)


def test_restore_keeps_collection_identity(make_app):
    app = make_app()
    controllers = app._controllers
    snapshot = snapshot_registrations(app)
    app.register_controller(Items)
    assert "Items" in app.controllers
    restore_registrations(app, snapshot)
    assert app._controllers is controllers
    assert "Items" not in app.controllers


class OverridingApp(Patera):
    """A subclass overriding methods whose bodies now live in the parts."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.calls: list[str] = []
        super().__init__(*args, **kwargs)

    def default_exception_response(
        self, req: Request, exc: Exception
    ) -> Optional[Response]:
        self.calls.append("default_exception_response")
        if isinstance(exc, RuntimeError):
            return req.res.json({"custom": str(exc)}).status(503)
        return super().default_exception_response(req, exc)

    async def abort_route_not_found(self, send):
        self.calls.append("abort_route_not_found")
        await self._send_error(send, 404, "Nothing here")

    def _log_request(self, scope, method: str, url_path: str) -> None:
        self.calls.append(f"request {method} {url_path}")
        super()._log_request(scope, method, url_path)

    def _log_response(self, req: Request, status_code: int) -> None:
        self.calls.append(f"response {status_code}")
        super()._log_response(req, status_code)

    async def send_response(self, res, send, response_type=None):
        res.set_header("x-sent-by", "override")
        return await super().send_response(res, send, response_type)


async def test_subclass_overrides_are_honoured(make_app, client_for):
    app: Any = make_app(controllers=[Items], app_base=OverridingApp)
    async with client_for(app) as client:
        ok = await client.get("/items")
        assert ok.status_code == 200
        assert ok.headers["x-sent-by"] == "override"

        missing = await client.get("/nowhere")
        assert missing.status_code == 404
        assert missing.json() == {"status": "error", "message": "Nothing here"}

        boom = await client.get("/items/boom")
        assert boom.status_code == 503
        assert boom.json() == {"custom": "boom"}

        teapot = await client.get("/items/teapot")
        assert teapot.status_code == 418

    assert "abort_route_not_found" in app.calls
    assert app.calls.count("default_exception_response") == 2
    assert "request GET /items" in app.calls
    assert "response 200" in app.calls
    assert "response 503" in app.calls


async def test_replaced_router_is_used_for_requests(make_app, client_for):
    # BaseExtension's rollback assigns app._router; the parts must read the
    # router from the app on every request, not keep their own reference.
    app = make_app()
    other = make_app(controllers=[Items])
    app._router = other._router
    async with client_for(app) as client:
        assert (await client.get("/items")).status_code == 200
