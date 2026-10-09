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
