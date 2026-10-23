"""Declarative pages, layouts and route authorization."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SubLayout:
    layout: type
    target: str = "#page"


@dataclass(frozen=True)
class Page:
    rule: str
    name: str | None = None
    title: Any = None
    layout: type | None = None
    sublayouts: tuple[SubLayout, ...] = ()
    target: str | None = None
    extras: dict = field(default_factory=dict)


def layout(cls):
    from .components import Component

    if not issubclass(cls, Component):
        raise TypeError("@layout requires a Component")
    if "__ui_page__" in vars(cls):
        raise ValueError("A page cannot also be a layout")
    cls.__ui_layout__ = True
    return cls


def auth(roles=()):
    if isinstance(roles, str):
        roles = (roles,)

    def decorate(target):
        target.__ui_auth__ = tuple(roles)
        return target

    return decorate


class AuthenticationError(PermissionError):
    pass


class AuthorizationError(PermissionError):
    pass


class ElementInitializationError(RuntimeError):
    pass
