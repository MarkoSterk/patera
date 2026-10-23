"""Small portable route matcher with explicit encoding and duplicate checks."""

import re
from typing import Any
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlencode

from .exceptions import NoRouteMatch

_VARIABLE = re.compile(r"<(?:(int|string|str|path):)?([A-Za-z_]\w*)>")
_PATTERNS = {"int": r"[0-9]+", "string": r"[^/]+", "path": r".+"}


@dataclass
class Route:
    rule: str
    endpoint: str
    handler: object
    regex: object
    parts: list
    converters: dict
    specificity: tuple


class Router:
    app: Any

    def __init__(self, strict_slashes=False):
        self.strict_slashes = strict_slashes
        self.routes = []
        self.endpoints = {}

    def normalize(self, value):
        return value if self.strict_slashes else value.rstrip("/") or "/"

    def add(self, rule, endpoint, handler):
        if not rule.startswith("/") or "?" in rule or "#" in rule:
            raise ValueError(f"Invalid page rule: {rule!r}")
        rule = self.normalize(rule)
        parts, converters, regex = [], {}, []
        offset = 0
        for match in _VARIABLE.finditer(rule):
            literal = rule[offset : match.start()]
            if "<" in literal or ">" in literal:
                raise ValueError(f"Invalid page rule: {rule}")
            parts.append((None, literal))
            regex.append(re.escape(literal))
            converter, name = match.groups()
            converter = "string" if converter in (None, "str") else converter
            if name in converters:
                raise ValueError(f"Duplicate route parameter: {name}")
            converters[name] = converter
            parts.append((converter, name))
            regex.append(f"(?P<{name}>{_PATTERNS[converter]})")
            offset = match.end()
        tail = rule[offset:]
        if "<" in tail or ">" in tail:
            raise ValueError(f"Invalid page rule: {rule}")
        parts.append((None, tail))
        regex.append(re.escape(tail))
        pattern = "".join(regex)
        # Parameter names cannot distinguish otherwise identical routes.
        shape = re.sub(r"\(\?P<[^>]+>", "(?:", pattern)
        for existing in self.routes:
            existing_shape = re.sub(r"\(\?P<[^>]+>", "(?:", existing.regex.pattern)
            if existing_shape == shape:
                raise ValueError(f"Duplicate page route: {rule}")
        existing = self.endpoints.get(endpoint)
        if existing and existing.handler != handler:
            raise ValueError(f"Duplicate page endpoint: {endpoint}")
        specificity = (
            sum(bool(s) and "<" not in s for s in rule.split("/")),
            -len(converters),
            sum(c == "int" for c in converters.values()),
            -sum(c == "path" for c in converters.values()),
            tuple(
                3
                if "<" not in segment
                else 2
                if "<int:" in segment
                else 0
                if "<path:" in segment
                else 1
                for segment in rule.split("/")
                if segment
            ),
            len(rule.split("/")),
        )
        route = Route(
            rule, endpoint, handler, re.compile(pattern), parts, converters, specificity
        )
        self.routes.append(route)
        self.routes.sort(key=lambda r: r.specificity, reverse=True)
        self.endpoints.setdefault(endpoint, route)

    def match(self, pathname):
        for route in self.routes:
            match = route.regex.fullmatch(self.normalize(pathname))
            if match:
                values = {}
                for name, value in match.groupdict().items():
                    converter = route.converters[name]
                    decoded = unquote(value, errors="strict")
                    if converter == "int":
                        decoded = int(decoded)
                    elif converter == "string" and "/" in decoded:
                        raise NoRouteMatch(pathname)
                    values[name] = decoded
                return route, values
        raise NoRouteMatch(pathname)

    def url_for(self, endpoint, *, query=None, **values):
        route = self.endpoints[endpoint]
        if set(values) != set(route.converters):
            raise ValueError(f"Expected parameters: {', '.join(route.converters)}")
        result = []
        for converter, value in route.parts:
            if converter is None:
                result.append(value)
                continue
            parameter = values[value]
            if converter == "int":
                if type(parameter) is not int or parameter < 0:
                    raise ValueError(f"{value} must be a nonnegative integer")
            elif not isinstance(parameter, str) or not parameter:
                raise ValueError(f"{value} must be a nonempty string")
            if converter == "string" and "/" in parameter:
                raise ValueError(f"{value} cannot contain slashes")
            result.append(
                quote(str(parameter), safe="/" if converter == "path" else "")
            )
        url = "".join(result)
        return url + ("?" + urlencode(query, doseq=True) if query else "")

    async def redirect(
        self, url, *, use_base_url=False, base_parameters=None, history="push"
    ):
        if use_base_url:
            values = {
                **(self.app.context.params if self.app.context else {}),
                **(base_parameters or {}),
            }
            base = Router()
            base.add(self.app.base_url or "/", "base", None)
            required = base.endpoints["base"].converters
            if set(required) - values.keys():
                raise ValueError("Missing base URL parameters")
            url = (
                base.url_for("base", **{key: values[key] for key in required}).rstrip(
                    "/"
                )
                + "/"
                + url.lstrip("/")
            )
        return await self.app.navigate(url, history=history)

    async def show_error_page(self, component, **options):
        return await self.app.show_error_page(component, **options)

    @property
    def route_parameters(self):
        return self.app.context.params if self.app.context else {}

    @property
    def current_route(self):
        return self.app.current_route
