"""
Dependency injection (Inject / ConfigVar) and extension config resolution.

This module deliberately uses ``from __future__ import annotations``: string
annotations used to make ``Inject[...]`` silently do nothing.
"""

from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel

from patera import BaseExtension
from patera.controller import Controller, get, path
from patera.injectable import Autowire, ConfigVar, Inject, declared_config_model


class GreeterConfig(BaseModel):
    GREETING: str = "Hello"
    PUNCTUATION: str = "!"


class Greeter(BaseExtension["object", GreeterConfig]):  # type: ignore[type-var]
    def greet(self, name: str) -> str:
        return f"{self.configs.GREETING} {name}{self.configs.PUNCTUATION}"


class RequiredConfig(BaseModel):
    URL: str


class NeedsConfig(BaseExtension["object", RequiredConfig]):  # type: ignore[type-var]
    pass


class Service(BaseExtension):
    greeter: Inject[Greeter]


class OtherService(BaseExtension):
    service: Annotated[Service, Autowire()]
    maybe: Optional[str] = None


def test_injection_overrides_follow_python_mro(make_app):
    class Plain(Service):
        greeter: str = "disabled"

    class Unannotated(Service):
        greeter = None

    class Grandchild(Plain):
        pass

    class Diamond(Plain, Service):
        pass

    class Reintroduced(Plain):
        greeter: Inject[Greeter]

    app = make_app()
    assert Plain(app).greeter == "disabled"
    assert Grandchild(app).greeter == "disabled"
    assert Diamond(app).greeter == "disabled"
    assert Unannotated(app).greeter is None
    assert isinstance(Reintroduced(app).greeter, Greeter)


def test_failed_extension_rolls_back_registrations(make_app):
    from patera.middleware import MiddlewareBase, middleware
    from werkzeug.exceptions import NotFound

    @middleware(order=123)
    class AddedMiddleware(MiddlewareBase):
        pass

    @path("/temporary")
    class AddedController(Controller):
        @get("")
        async def index(self, req):
            return req.res.text("temporary")

    class Broken(BaseExtension):
        attempts = 0

        def init(self):
            type(self).attempts += 1
            self.app.register_middleware(AddedMiddleware)
            self.app.register_controller(AddedController)
            self.app.add_on_shutdown_method(lambda: None)
            self.app.add_template_path("temporary-templates")
            self.app.register_alias("temporary-alias", "AddedController.index")
            raise RuntimeError("failed initialization")

    Consumer = type(
        "Consumer",
        (BaseExtension,),
        {"__annotations__": {"dependency": Inject[Broken]}},
    )
    app = make_app()
    shutdown = list(app._on_shutdown_methods)
    for constructor in (Broken, Consumer, Consumer):
        with pytest.raises(RuntimeError, match="failed initialization"):
            constructor(app)
        assert "BROKEN" not in app.extensions
        assert "CONSUMER" not in app.extensions
        assert AddedMiddleware not in app._middleware_classes.values()
        assert app._on_shutdown_methods == shutdown
        assert "temporary-templates" not in app._all_templates_paths
        assert "temporary-alias" not in app._url_for_alias
        with pytest.raises(NotFound):
            app.router.match("/temporary", "GET")
    assert Broken.attempts == 3


@path("/greet")
class GreetController(Controller):
    greeter: Inject[Greeter]
    app_name: str = ConfigVar("APP_NAME")
    missing: str = ConfigVar("NOT_THERE", "fallback")

    @get("/")
    async def greet(self, req):
        return req.res.text(self.greeter.greet(self.app_name))


def test_inject_works_with_string_annotations(make_app):
    app = make_app(controllers=[GreetController])
    ctrl = app.get_controller(GreetController)
    assert isinstance(ctrl.greeter, Greeter)
    # Singleton per app
    assert app.get_extension(Greeter) is ctrl.greeter


def test_config_var_descriptor(make_app):
    app = make_app(controllers=[GreetController], APP_NAME="My app")
    ctrl = app.get_controller(GreetController)
    assert ctrl.app_name == "My app"
    assert ctrl.missing == "fallback"
    with pytest.raises(AttributeError):
        ctrl.app_name = "other"


def test_nested_injection(make_app):
    app = make_app(extensions=[OtherService])
    other = app.get_extension(OtherService)
    assert isinstance(other.service, Service)
    assert isinstance(other.service.greeter, Greeter)


def test_extension_config_defaults_when_missing(make_app):
    app = make_app()
    greeter = Greeter(app)
    assert greeter.greet("Ana") == "Hello Ana!"


def test_extension_config_from_dict_and_model(make_app):
    app = make_app(GREETER={"GREETING": "Hi"})
    assert Greeter(app).greet("Bo") == "Hi Bo!"

    app2 = make_app(GREETER=GreeterConfig(GREETING="Hey", PUNCTUATION="?"))
    assert Greeter(app2).greet("Cy") == "Hey Cy?"


def test_extension_missing_required_config_raises(make_app):
    app = make_app()
    with pytest.raises(TypeError, match="NEEDS_CONFIG"):
        NeedsConfig(app).configs


def test_declared_config_model_walks_hierarchy():
    class Sub(Greeter):
        pass

    assert declared_config_model(Sub, BaseExtension) is GreeterConfig
    assert declared_config_model(Service, BaseExtension) is None


def test_get_extension_errors(make_app):
    app = make_app()
    with pytest.raises(KeyError):
        app.get_extension(Greeter)


def test_unresolvable_injection_is_reported():
    with pytest.raises(TypeError, match="Could not resolve the injected annotation"):

        class Broken(BaseExtension):  # noqa: F841
            dep: Inject[DoesNotExist]  # type: ignore[name-defined]  # noqa: F821
