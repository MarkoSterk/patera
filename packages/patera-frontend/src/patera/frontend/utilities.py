"""
Utility methods
"""

import re
from typing import Dict, Any, Optional, Callable
from js import window, CustomEvent
import inspect

from .exceptions.exceptions import AppDataException


class NullAttrs:
    def __init__(self, value: Optional[Dict[str, Any]] = None):
        if value is None:
            value = {}
        for key, val in value.items():
            if isinstance(val, dict):
                val = NullAttrs(val)
            setattr(self, key, val)

    def __getattr__(self, name):
        return None


class AppData(NullAttrs):
    def __init__(self, data: Optional[Dict[str, Any]] = None):
        if data is None:
            data = {}

        object.__setattr__(self, "_initial_keys", list(data.keys()))

        for key, value in data.items():
            if isinstance(value, dict):
                value = NullAttrs(value)
            setattr(self, key, value)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_initial_keys":
            object.__setattr__(self, name, value)
            return

        initial_keys = object.__getattribute__(self, "_initial_keys")
        if name not in initial_keys:
            raise AppDataException(
                f"Data under {name=} does not exist. Please set initial data with {name=} in application data"
            )

        if isinstance(value, dict):
            value = NullAttrs(value)

        super().__setattr__(name, value)

        event = CustomEvent.new(
            "app:data-change", {"detail": {"name": name, "value": value}}
        )

        window.dispatchEvent(event)


class RouteParams(NullAttrs):
    """Route parameters"""

    def __init__(self, params: Dict[str, Any]):
        super().__init__()
        for key, value in params.items():
            setattr(self, key, value)


class PageAttributes(NullAttrs):
    """Page attributes from path decorator"""

    def __init__(self, attrs: Dict[str, Any]):
        super().__init__()
        for key, value in attrs.items():
            setattr(self, key, value)


def _pascal_to_kebab(name: str) -> str:
    # "PyCounter" -> "py-counter"
    return re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()


def html(markup: str) -> str:
    s = markup.strip()

    # event handler replacing
    s = re.sub(r'@([a-zA-Z_][\w-]*)="([^"]*)"', r'jolt-\1="\2"', s)

    # 2) Replace PascalCase self-closing tags:
    #    <PyCounter .../> -> <py-counter ...></py-counter>
    def repl_self_closing(m: re.Match) -> str:
        tag = m.group("tag")
        attrs = m.group("attrs") or ""
        kebab = _pascal_to_kebab(tag)
        return f"<{kebab}{attrs}></{kebab}>"

    s = re.sub(
        r"<(?P<tag>[A-Z][A-Za-z0-9]*)"  # PascalCase tag name
        r"(?P<attrs>(?:\s+[^<>]*?)?)"  # attributes (optional)
        r"\s*/>",  # self-closing
        repl_self_closing,
        s,
    )

    # 3) Replace PascalCase opening tags (non-self-closing):
    #    <PyCounter ...> -> <py-counter ...>
    def repl_open(m: re.Match) -> str:
        tag = m.group("tag")
        attrs = m.group("attrs") or ""
        kebab = _pascal_to_kebab(tag)
        return f"<{kebab}{attrs}>"

    s = re.sub(
        r"<(?P<tag>[A-Z][A-Za-z0-9]*)"  # PascalCase tag name
        r"(?P<attrs>(?:\s+[^<>]*?)?)"  # attributes (optional)
        r">",  # normal open
        repl_open,
        s,
    )

    # 4) Replace PascalCase closing tags:
    #    </PyCounter> -> </py-counter>
    def repl_close(m: re.Match) -> str:
        tag = m.group("tag")
        kebab = _pascal_to_kebab(tag)
        return f"</{kebab}>"

    s = re.sub(r"</(?P<tag>[A-Z][A-Za-z0-9]*)\s*>", repl_close, s)

    return s


def css(style: str) -> str:
    return style.strip()


async def run_sync_or_async(func: Callable, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return func(*args, **kwargs)
