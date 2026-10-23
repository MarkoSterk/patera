"""Portable UI definitions; browser and server adapters are loaded on demand."""

from typing import TYPE_CHECKING

from .application import Application, PageContext
from .components import Component, State, event, tag
from .controller import Controller, page, path
from .exceptions import APIError, ExceptionHandler, NoRouteMatch, handles
from .view import View, Template, TemplateEngine, template, html, trusted_html
from .lifecycle import Lifecycle, lifecycle, ElementDisconnectedError
from .metadata import (
    layout,
    auth,
    SubLayout,
    AuthenticationError,
    AuthorizationError,
    ElementInitializationError,
)
from .properties import react, react_factory, query_param, select, select_all
from .cache import lazy, DependencyLoadError
from .exceptions import NetworkError, JsonResponseError

if TYPE_CHECKING:
    from .server import DesktopUI, DesktopUIConfig

__all__ = [
    "Template",
    "TemplateEngine",
    "template",
    "Lifecycle",
    "lifecycle",
    "ElementDisconnectedError",
    "layout",
    "auth",
    "SubLayout",
    "AuthenticationError",
    "AuthorizationError",
    "ElementInitializationError",
    "react",
    "react_factory",
    "query_param",
    "select",
    "select_all",
    "lazy",
    "DependencyLoadError",
    "NetworkError",
    "JsonResponseError",
    "APIError",
    "Application",
    "Component",
    "Controller",
    "DesktopUI",
    "DesktopUIConfig",
    "ExceptionHandler",
    "NoRouteMatch",
    "PageContext",
    "State",
    "View",
    "event",
    "handles",
    "html",
    "page",
    "path",
    "tag",
    "trusted_html",
]


def __getattr__(name):
    if name in {"DesktopUI", "DesktopUIConfig"}:
        from .server import DesktopUI, DesktopUIConfig

        return {"DesktopUI": DesktopUI, "DesktopUIConfig": DesktopUIConfig}[name]
    raise AttributeError(name)
