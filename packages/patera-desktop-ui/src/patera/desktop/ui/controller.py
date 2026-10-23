"""Page controller metadata, independent of Patera's HTTP controllers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar
from .lifecycle import effective_methods
from .metadata import Page

if TYPE_CHECKING:
    from .application import Application

F = TypeVar("F", bound=Callable[..., Any])
C = TypeVar("C", bound="Controller")


def path(prefix: str) -> Callable[[type[C]], type[C]]:
    def decorate(cls):
        cls.__ui_path__ = prefix
        return cls

    return decorate


def page(
    rule: str,
    *,
    name: str | None = None,
    title=None,
    layout=None,
    sublayouts=(),
    target=None,
    extras=None,
):
    def decorate(function):
        if isinstance(function, type):
            from .components import Component

            if not issubclass(function, Component) or "__ui_layout__" in vars(function):
                raise TypeError("Class pages must be Components, not layouts")
            function.__ui_page__ = Page(
                rule, name, title, layout, tuple(sublayouts), target, dict(extras or {})
            )
            return function
        function.__ui_page_options__ = Page(
            rule, name, title, layout, tuple(sublayouts), target, dict(extras or {})
        )
        function.__ui_pages__ = (*getattr(function, "__ui_pages__", ()), (rule, name))
        return function

    return decorate


def methods(instance):
    yield from effective_methods(instance)


class Controller:
    def __init__(self, app: Application) -> None:
        self.app = app

    def routes(self) -> Iterator[tuple[str, str, Callable]]:
        for name, method in methods(self):
            for rule, endpoint in getattr(method, "__ui_pages__", ()):
                prefix = getattr(self, "__ui_path__", "")
                full = re.sub(
                    r"/{2,}", "/", "/" + prefix.strip("/") + "/" + rule.lstrip("/")
                )
                if not rule and full != "/":
                    full = full.rstrip("/")
                yield full, endpoint or f"{type(self).__name__}.{name}", method
