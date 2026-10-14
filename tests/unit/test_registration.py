"""
Registration and injection: duplicate routes, dependency cycles, name
collisions, logger and exception handler registration, and controller aliases.
"""

from __future__ import annotations

import pytest

from patera import BaseExtension, Request, Response
from patera.controller import Controller, get, path
from patera.exceptions import (
    CircularDependencyError,
    DuplicateRouteError,
    ExceptionHandler,
    exception_handler,
    handles,
)
from patera.exceptions.http_exceptions import (
    BaseHttpException,
    StaticPageNotFound,
    html_abort,
)
from patera.injectable import AutowireDef, Inject

# ---- Duplicate routes ---------------------------------------------------------


@path("/dup")
class DuplicateRoutes(Controller):
    @get("/")
    async def first(self, req: Request) -> Response:
        return req.res.text("first")

    @get("/")
    async def second(self, req: Request) -> Response:
        return req.res.text("second")


@path("/alias")
class SameFunctionTwice(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("index")

    home = index  # the same handler under a second attribute name


@path("/shared")
class SharedOne(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("one")


@path("/shared")
class SharedTwo(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("two")


@path("/shared")
class SharedOtherMethod(Controller):
    @get("/other")
    async def index(self, req: Request) -> Response:
        return req.res.text("other")


def test_duplicate_route_in_one_controller_is_rejected(make_app):
    with pytest.raises(DuplicateRouteError, match="'first' and 'second'"):
        make_app(controllers=[DuplicateRoutes])


def test_same_function_under_two_names_is_one_route(make_app, client_for):
    app = make_app(controllers=[SameFunctionTwice])
    endpoints = app.get_controller(SameFunctionTwice).endpoints_map["GET"]
    assert list(endpoints) == ["/"]


def test_duplicate_route_across_controllers_is_rejected(make_app):
    with pytest.raises(DuplicateRouteError, match="GET '/shared/'"):
        make_app(controllers=[SharedOne, SharedTwo])


async def test_controllers_may_share_a_base_path(make_app, client_for):
    app = make_app(controllers=[SharedOne, SharedOtherMethod])
    async with client_for(app) as client:
        assert (await client.get("/shared/")).text == "one"
        assert (await client.get("/shared/other")).text == "other"


# ---- Controller aliases ---------------------------------------------------------


@path("/posts", alias="posts")
class PostsController(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("posts")


def test_controller_alias_builds_method_urls(make_app):
    app = make_app(controllers=[PostsController])
    assert app.url_for("posts.index") == "/posts/"
    assert app.url_for("PostsController.index") == "/posts/"
    # The bare alias is not an endpoint, so it is not recorded as one.
    assert "posts" not in app._url_for_alias
    with pytest.raises(ValueError):
        app.url_for("posts")


# ---- Dependency cycles ------------------------------------------------------


class ServiceA(BaseExtension):
    pass


class ServiceB(BaseExtension):
    other: Inject[ServiceA]


# Injections are resolved when a class is defined, so a cycle cannot be
# written as two annotations. It can still arise when injection metadata is
# assembled later (for example by a class decorator or a plugin); the guard
# turns it into a clear error instead of a RecursionError.
ServiceA.__autowires__ = {
    "other": AutowireDef(name="other", declared_type=ServiceB, target_type=ServiceB)
}


class SelfInjecting(BaseExtension):
    pass


SelfInjecting.__autowires__ = {
    "me": AutowireDef(name="me", declared_type=SelfInjecting, target_type=SelfInjecting)
}


class Leaf(BaseExtension):
    pass


class UsesLeaf(BaseExtension):
    leaf: Inject[Leaf]


def test_dependency_cycle_is_reported(make_app):
    with pytest.raises(CircularDependencyError) as exc:
        make_app(extensions=[ServiceA])
    assert "ServiceA -> ServiceB -> ServiceA" in str(exc.value)


def test_self_injection_is_reported(make_app):
    with pytest.raises(CircularDependencyError, match="SelfInjecting -> SelfInjecting"):
        make_app(extensions=[SelfInjecting])


def test_shared_dependencies_are_not_cycles(make_app):
    app = make_app(extensions=[UsesLeaf, Leaf])
    uses = app.get_extension(UsesLeaf)
    assert uses.leaf is app.get_extension(Leaf)
    assert app.__dict__["_resolving_dependencies"] == []


# ---- Name collisions ----------------------------------------------------------


class Cache(BaseExtension):
    pass


FirstCache = Cache


class Cache(BaseExtension):  # type: ignore[no-redef]  # noqa: F811
    pass


SecondCache = Cache


@path("/cache")
class UsesSecondCache(Controller):
    cache: Inject[SecondCache]

    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("x")


def test_injecting_a_class_with_a_taken_name_fails(make_app):
    with pytest.raises(TypeError, match="registry slot 'CACHE'"):
        make_app(extensions=[FirstCache], controllers=[UsesSecondCache])


def test_injection_still_works_without_a_collision(make_app):
    app = make_app(controllers=[UsesSecondCache])
    ctrl = app.get_controller(UsesSecondCache)
    assert isinstance(ctrl.cache, SecondCache)


# ---- Loggers ------------------------------------------------------------------

LOGGER_FILES = {
    "loggers/audit_logger.py": """
        from patera.logging import LoggerBase, logger

        @logger()
        class AuditLogger(LoggerBase):
            pass
    """,
}


def test_logger_imported_twice_adds_one_sink(make_app):
    single = make_app(
        files=LOGGER_FILES,
        AUDIT_LOGGER={"LEVEL": "ERROR", "ENQUEUE": False},
    )
    files = {
        **LOGGER_FILES,
        "loggers/second_logger.py": """
            from .audit_logger import AuditLogger  # noqa: F401
        """,
    }
    twice = make_app(files=files, AUDIT_LOGGER={"LEVEL": "ERROR", "ENQUEUE": False})
    assert len(twice._logger_sink_ids) == len(single._logger_sink_ids)
    assert len(twice._registered_loggers) == 1


# ---- Exception handlers ---------------------------------------------------------


def _make_boom():
    class Boom(Exception):
        pass

    return Boom


BoomOne = _make_boom()
BoomTwo = _make_boom()


@exception_handler
class BoomHandler(ExceptionHandler):
    @handles(BoomOne)
    async def boom(self, req, exc):
        return req.res.text("handled").status(418)


def test_handlers_are_keyed_by_class_not_name(make_app):
    app = make_app(exception_handlers=[BoomHandler])
    assert BoomOne.__name__ == BoomTwo.__name__
    assert app._find_exception_handler(BoomOne()) is not None
    assert app._find_exception_handler(BoomTwo()) is None


def test_handler_classes_with_the_same_name_conflict(make_app):
    first = BoomHandler

    @exception_handler
    class BoomHandler2(ExceptionHandler):
        @handles(BoomTwo)
        async def boom(self, req, exc):
            return req.res.text("other")

    BoomHandler2.__name__ = "BoomHandler"
    app = make_app(exception_handlers=[first])
    with pytest.raises(ValueError, match="already registered"):
        app.register_exception_handler(BoomHandler2)


@path("/builtin")
class BuiltinErrors(Controller):
    @get("/page")
    async def page(self, req: Request) -> Response:
        raise StaticPageNotFound("missing")

    @get("/html")
    async def html(self, req: Request) -> Response:
        html_abort("error.html", 409, {"reason": "conflict"})
        return req.res.text("unreachable")


@exception_handler
class StaticPageHandler(ExceptionHandler):
    @handles(StaticPageNotFound)
    async def missing(self, req, exc):
        return req.res.text("custom missing page").status(404)


@exception_handler
class GenericHttpHandler(ExceptionHandler):
    @handles(BaseHttpException)
    async def generic(self, req, exc):
        return req.res.json({"generic": True}).status(exc.status_code)


BUILTIN_FILES = {"templates/error.html": "Conflict: {{ reason }}"}


async def test_builtin_exceptions_without_handlers(make_app, client_for):
    app = make_app(controllers=[BuiltinErrors], files=BUILTIN_FILES)
    async with client_for(app) as client:
        res = await client.get("/builtin/page")
        assert res.status_code == 404
        assert res.json()["message"] == "Endpoint not found"
        res = await client.get("/builtin/html")
        assert res.status_code == 409
        assert res.text == "Conflict: conflict"


async def test_builtin_exceptions_use_their_own_handlers(make_app, client_for):
    app = make_app(
        controllers=[BuiltinErrors],
        exception_handlers=[StaticPageHandler],
        files=BUILTIN_FILES,
    )
    async with client_for(app) as client:
        res = await client.get("/builtin/page")
        assert res.status_code == 404
        assert res.text == "custom missing page"


async def test_generic_handlers_do_not_capture_builtin_exceptions(make_app, client_for):
    app = make_app(
        controllers=[BuiltinErrors],
        exception_handlers=[GenericHttpHandler],
        files=BUILTIN_FILES,
    )
    async with client_for(app) as client:
        res = await client.get("/builtin/page")
        assert res.json()["message"] == "Endpoint not found"
        res = await client.get("/builtin/html")
        assert res.text == "Conflict: conflict"


def test_middleware_order_zero_is_kept(make_app):
    from patera.middleware import MiddlewareBase

    class ZeroOrder(MiddlewareBase):
        _middleware = True

        async def middleware(self, req):
            return await self.next(req)

    app = make_app()
    app.register_middleware(ZeroOrder, order=0)
    assert app._middleware_classes[0] is ZeroOrder


def test_framework_middleware_declare_their_default_order():
    from patera.cors.cors_mw import CORSMiddleware
    from patera.auth import Authentication
    from patera.database.sql.sql_database_manager import SqlDatabaseManagerMiddleware

    # One attribute for framework positions; "_order" is set by @middleware.
    assert CORSMiddleware._order_ == -101
    assert SqlDatabaseManagerMiddleware._order_ == -100
    assert Authentication._order_ == -99
    assert "_order" not in vars(SqlDatabaseManagerMiddleware)


# ---- Controllers: properties, same names, sockets -------------------------------


@path("/with-property")
class ControllerWithProperty(Controller):
    @property
    def user(self):
        from patera.ctx import current_request

        # Needs a request: must not be read while the controller registers.
        return current_request.user

    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.json({"user": self.user})


async def test_controller_properties_are_not_read_at_registration(make_app, client_for):
    app = make_app(controllers=[ControllerWithProperty])
    async with client_for(app) as client:
        res = await client.get("/with-property/")
    assert res.json() == {"user": None}


def _api(prefix: str) -> type:
    @path(prefix)
    class Api(Controller):
        @get("/")
        async def index(self, req: Request) -> Response:
            return req.res.json({})

    return Api


def test_two_controllers_with_one_name_are_refused(make_app):
    with pytest.raises(ValueError, match="Two controllers are named 'Api'"):
        make_app(controllers=[_api("/users"), _api("/posts")])


def test_registering_the_same_controller_twice_is_harmless(make_app):
    api = _api("/users")
    app = make_app(controllers=[api])
    app.register_controller(api)
    assert app.get_controller("Api").__class__ is api


def test_socket_handlers_refuse_middleware_decorators(make_app):
    from patera.controller import socket

    def protected(func):
        # What @login_required() / @role_required(...) leave on a handler.
        func._authentication = {"required": True}
        return func

    @path("/ws")
    class LoginSocket(Controller):
        @socket("/chat")
        @protected
        async def chat(self, req: Request) -> None: ...

    with pytest.raises(ValueError, match="HTTP middleware does not run"):
        make_app(controllers=[LoginSocket])

    @path("/ws2")
    class TransactionalSocket(Controller):
        @socket("/chat")
        async def chat(self, req: Request) -> None: ...

    TransactionalSocket._transactional = True  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="@transactional"):
        make_app(controllers=[TransactionalSocket])


def test_the_missing_configuration_error_names_the_app_decorator():
    from patera import Patera
    from patera.patera import MissingAppConfigurations

    class Undecorated(Patera):  # type: ignore[type-arg]
        pass

    with pytest.raises(MissingAppConfigurations, match=r"@app\(__name__"):
        Undecorated()
