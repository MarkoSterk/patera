"""Jinja2 rendering shared by native tests and the offline browser runtime."""

from __future__ import annotations
import re
from html.parser import HTMLParser
from types import CellType, FunctionType
from typing import Any
from jinja2 import DictLoader, Environment, StrictUndefined, nodes
from jinja2.ext import Extension
from jinja2.runtime import Macro
from markupsafe import Markup

TrustedHTML = Markup


def trusted_html(value: str) -> Markup:
    return Markup(value)


class _Bindings(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source, self.inserts, self.stack = source, [], []
        self.offsets = [0]
        for line in source.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))

    def position(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag in {
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
        }:
            return
        binding = dict(attrs).get("data-bind")
        self.stack.append((tag, binding))
        if binding:
            self.inserts.append(
                (
                    self.position() + len(self.get_starttag_text()),
                    "{% bind " + repr(binding) + " %}",
                )
            )

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if self.stack[-1][0] != tag:
            if any(t == tag and binding for t, binding in self.stack):
                raise ValueError("data-bind requires balanced HTML elements")
            return
        _, binding = self.stack.pop()
        if binding:
            self.inserts.append((self.position(), "{% endbind %}"))


def binding_blocks(source):
    parser = _Bindings(source)
    masked = re.sub(
        r"{%-?\s*raw\s*-?%}.*?{%-?\s*endraw\s*-?%}|{{.*?}}|{%.*?%}|{#.*?#}",
        lambda m: re.sub(r"[^\n]", " ", m[0]),
        source,
        flags=re.S,
    )
    parser.feed(masked)
    for position, value in reversed(sorted(parser.inserts)):
        source = source[:position] + value + source[position:]
    return source


def freeze_macro(macro):
    """Snapshot loop-local cells while retaining referenced reactive objects."""
    fn = macro._func
    frozen = FunctionType(
        fn.__code__,
        fn.__globals__,
        fn.__name__,
        fn.__defaults__,
        tuple(CellType(cell.cell_contents) for cell in fn.__closure__)
        if fn.__closure__
        else None,
    )
    return Macro(
        macro._environment,
        frozen,
        macro.name,
        macro.arguments,
        macro.catch_kwargs,
        macro.catch_varargs,
        macro.caller,
        macro._default_autoescape,
    )


class BindingExtension(Extension):
    tags = {"bind"}

    def preprocess(self, source, name, filename=None):
        return binding_blocks(source)

    def parse(self, parser):
        token = next(parser.stream)
        binding = parser.parse_expression()
        body = parser.parse_statements(("name:endbind",), drop_needle=True)
        call = self.call_method("capture", [nodes.ContextReference(), binding])
        return nodes.CallBlock(call, [], [], body).set_lineno(token.lineno)

    def capture(self, context, binding, caller):
        renderer = context.get("_ui_renderer")
        return (
            caller()
            if renderer is None
            else renderer.capture(str(binding), freeze_macro(caller))
        )


class Rendered:
    def __init__(self, engine, context):
        self.engine, self.context = engine, context
        self.fragments, self.parents, self.stack = {}, {}, []
        self.counter = 0

    def capture(self, binding, caller):
        self.counter += 1
        identifier = str(self.counter)
        self.fragments[identifier] = (binding, caller)
        self.parents[identifier] = self.stack[-1] if self.stack else None
        self.stack.append(identifier)
        try:
            value = caller()
        finally:
            self.stack.pop()
        return Markup(f"<!--ui-bind:{identifier}-->{value}<!--/ui-bind:{identifier}-->")

    def refresh(self, binding):
        previous = (dict(self.fragments), dict(self.parents), self.counter)
        try:
            return self._refresh(binding)
        except Exception:
            self.fragments, self.parents, self.counter = previous
            raise

    def _refresh(self, binding):
        selected = {key for key, (name, _) in self.fragments.items() if name == binding}
        result = []
        for key in list(self.fragments):
            if key not in selected:
                continue
            ancestor, ancestors = self.parents.get(key), []
            while ancestor:
                ancestors.append(ancestor)
                ancestor = self.parents.get(ancestor)
            if selected.intersection(ancestors):
                continue
            caller = self.fragments[key][1]
            obsolete = []
            for child in list(self.fragments):
                parent = self.parents.get(child)
                while parent:
                    if parent == key:
                        obsolete.append(child)
                        break
                    parent = self.parents.get(parent)
            for child in obsolete:
                self.fragments.pop(child, None)
                self.parents.pop(child, None)
            self.stack.append(key)
            try:
                result.append((key, str(caller())))
            finally:
                self.stack.pop()
        return result


class Template:
    def __init__(self, source=None, *, name=None, **context):
        if (source is None) == (name is None):
            raise ValueError("Provide source or name")
        self.source, self.name, self.context = source, name, context


def template(source=None, *, name=None, **context):
    return Template(source, name=name, **context)


class TemplateEngine:
    def __init__(self, templates=None, *, filters=None, globals=None):
        self.environment = Environment(
            loader=DictLoader(templates if templates is not None else {}),
            autoescape=True,
            undefined=StrictUndefined,
            extensions=[BindingExtension],
        )
        self.environment.filters.update(filters or {})
        self.environment.globals.update(globals or {})

    def render(self, value: Template, **context):
        compiled = (
            self.environment.get_template(value.name)
            if value.name
            else self.environment.from_string(value.source)
        )
        renderer = Rendered(self, {**context, **value.context})
        markup = compiled.render(**renderer.context, _ui_renderer=renderer)
        return Markup(markup), renderer


def html(source: str, **values: Any) -> Markup:
    return TemplateEngine().render(Template(source, **values))[0]


class View:
    def __init__(self, template=None, *, markup=None, title=None, **context):
        if (template is None) == (markup is None):
            raise ValueError("Provide exactly one of template or markup")
        self.template, self.markup, self.title, self.context = (
            template,
            markup,
            title,
            context,
        )

    def render(self, templates):
        if isinstance(self.markup, Markup) and not self.context:
            return self.markup
        engine = (
            templates
            if isinstance(templates, TemplateEngine)
            else TemplateEngine(templates)
        )
        return engine.render(Template(self.markup, name=self.template, **self.context))[
            0
        ]


class ComponentView(View):
    def __init__(self, component, metadata, context, args=None, content=None):
        self.component, self.metadata, self.page_context = component, metadata, context
        self.args = args or {}
        self.content = content
        self.title = metadata.title

    def render(self, templates):
        return Markup("")
