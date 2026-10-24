"""Opt-in Jinja keyed ranges and fixed-height virtual windows."""

from collections.abc import Mapping
from html.parser import HTMLParser
from math import ceil, isfinite

from jinja2 import nodes
from jinja2.ext import Extension
from markupsafe import Markup, escape


class _KeyValidator(HTMLParser):
    void = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.stack = []
        self.keys = set()

    def handle_starttag(self, tag, attrs):
        names = [name for name, _ in attrs]
        if len(names) != len(set(names)):
            raise ValueError("Keyed row HTML cannot contain duplicate attributes")
        if not self.depth:
            key = dict(attrs).get("data-ui-key")
            if not key or key in self.keys:
                raise ValueError(
                    "Keyed rows require unique, non-empty data-ui-key values"
                )
            self.keys.add(key)
        if tag not in self.void:
            self.depth += 1
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise ValueError("Keyed rows require balanced HTML")
        self.stack.pop()
        self.depth -= 1

    def handle_startendtag(self, tag, attrs):
        if (
            tag not in self.void
            and tag not in {"svg", "math"}
            and not {"svg", "math"}.intersection(self.stack)
        ):
            raise ValueError("Non-void HTML elements require explicit closing tags")
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if not self.depth and data.strip():
            raise ValueError("Keyed ranges contain element rows, not bare text")

    def handle_comment(self, data):
        if not self.depth:
            raise ValueError("Place nested bindings inside a keyed row")


def validate_keys(markup):
    parser = _KeyValidator()
    parser.feed(str(markup))
    parser.close()
    if parser.depth:
        raise ValueError("Keyed rows require balanced HTML")
    return markup


def window_bounds(count, scroll_top, row_height, height, overscan):
    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value > 0
        for value in (row_height, height)
    ):
        raise ValueError(
            "Virtual row_height and height must be positive finite numbers"
        )
    if not isinstance(overscan, int) or isinstance(overscan, bool) or overscan < 0:
        raise ValueError("Virtual overscan must be a non-negative integer")
    top = min(max(0, scroll_top), max(0, count * row_height - height))
    start = max(0, int(top // row_height) - overscan)
    end = min(count, ceil((top + height) / row_height) + overscan)
    return start, end, top


class ListExtension(Extension):
    tags = {"keyed", "virtual"}

    def parse(self, parser):
        token = next(parser.stream)
        binding = parser.parse_expression()
        if token.value == "keyed":
            body = parser.parse_statements(("name:endkeyed",), drop_needle=True)
            return nodes.CallBlock(
                self.call_method(
                    "capture", [nodes.ContextReference(), binding, nodes.Const("keyed")]
                ),
                [],
                [],
                body,
            ).set_lineno(token.lineno)
        parser.stream.expect("comma")
        items = parser.parse_expression()
        options = {
            "key": nodes.Const("id"),
            "row_height": nodes.Const(40),
            "height": nodes.Const(400),
            "overscan": nodes.Const(3),
        }
        supplied = set()
        while parser.stream.skip_if("comma"):
            name = parser.stream.expect("name").value
            if name not in options or name in supplied:
                parser.fail(f"Unknown or repeated virtual option: {name}", token.lineno)
            supplied.add(name)
            parser.stream.expect("assign")
            options[name] = parser.parse_expression()
        body = parser.parse_statements(("name:endvirtual",), drop_needle=True)
        rows = nodes.CallBlock(
            self.call_method(
                "rows", [nodes.ContextReference(), items, *options.values()]
            ),
            [nodes.Name("item", "param"), nodes.Name("index", "param")],
            [],
            body,
        )
        # The outer macro reevaluates the items expression on every invalidation.
        return nodes.CallBlock(
            self.call_method(
                "capture", [nodes.ContextReference(), binding, nodes.Const("virtual")]
            ),
            [],
            [],
            [rows],
        ).set_lineno(token.lineno)

    def capture(self, context, binding, mode, caller):
        from .view import freeze_macro

        renderer = context.get("_ui_renderer")
        if renderer is None:
            raise ValueError("List blocks require a UI template renderer")
        return renderer.capture(str(binding), freeze_macro(caller), mode=mode)

    def rows(self, context, items, key, row_height, height, overscan, caller):
        renderer = context.get("_ui_renderer")
        identifier = renderer.stack[-1]
        items = list(items)
        keys, seen = [], set()
        for item in items:
            value = (
                key(item)
                if callable(key)
                else item[key]
                if isinstance(item, Mapping)
                else getattr(item, key)
            )
            if (
                isinstance(value, bool)
                or not isinstance(value, (str, int))
                or not str(value)
            ):
                raise ValueError("Virtual keys must be non-empty strings or integers")
            value = str(value)
            if value in seen:
                raise ValueError(f"Duplicate virtual key: {value}")
            seen.add(value)
            keys.append(value)
        start, end, top = window_bounds(
            len(items),
            renderer.virtual_offsets.get(identifier, 0),
            row_height,
            height,
            overscan,
        )
        renderer.virtual_offsets[identifier] = top
        renderer.virtual_windows[identifier] = (
            len(items),
            row_height,
            height,
            overscan,
            start,
            end,
        )
        content = []
        for index in range(start, end):
            content.append(
                f'<div data-ui-key="{escape(keys[index])}" role="listitem" aria-posinset="{index + 1}" aria-setsize="{len(items)}" style="height:{row_height}px;box-sizing:border-box;overflow:hidden">{caller(items[index], index)}</div>'
            )
        return Markup(
            f'<div data-ui-virtual="{identifier}" data-ui-scroll-top="{top}" role="list" tabindex="0" style="height:{height}px;overflow:auto;overflow-anchor:none">'
            f'<div aria-hidden="true" style="height:{start * row_height}px"></div>'
            '<div data-ui-rows="">' + "".join(content) + "</div>"
            f'<div aria-hidden="true" style="height:{(len(items) - end) * row_height}px"></div></div>'
        )
