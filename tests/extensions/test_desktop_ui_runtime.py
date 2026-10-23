"""Behavioral contracts carried over from JoltUI, without a browser runtime."""

import asyncio
from types import SimpleNamespace, ModuleType

import pytest

from patera.desktop.ui import (
    Application,
    Component,
    Lifecycle,
    SubLayout,
    TemplateEngine,
    View,
    auth,
    handles,
    ExceptionHandler,
    layout,
    lifecycle,
    page,
    react,
    react_factory,
    tag,
    template,
    lazy,
    AuthenticationError,
)
from patera.desktop.ui.cache import TemplateCache
from patera.desktop.ui.lifecycle import Scope, run_hooks
from patera.desktop.ui.metadata import ElementInitializationError


def test_jinja_inheritance_macros_filters_autoescaping_and_loop_bindings():
    engine = TemplateEngine(
        {
            "base.html": "<main>{% block body %}{% endblock %}</main>",
            "macros.html": "{% macro label(value) %}<b>{{ value }}</b>{% endmacro %}",
            "list.html": '{% extends "base.html" %}{% from "macros.html" import label %}'
            '{% block body %}{% for row in rows %}<p data-bind="count">'
            "{{ label(row) }}:{{ component.count|twice }}</p>{% endfor %}{% endblock %}",
        },
        filters={"twice": lambda n: n * 2},
    )
    component = SimpleNamespace(count=1)
    markup, rendered = engine.render(
        template(name="list.html", rows=["<A>", "B"]), component=component
    )
    assert "<b>&lt;A&gt;</b>:2" in markup
    assert str(markup).startswith("<main>")
    component.count = 3
    fragments = rendered.refresh("count")
    assert [text for _, text in fragments] == ["<b>&lt;A&gt;</b>:6", "<b>B</b>:6"]


def test_nested_bindings_discard_obsolete_closures_and_do_not_double_refresh():
    component = SimpleNamespace(items=[1, 2])
    engine = TemplateEngine()
    _, rendered = engine.render(
        template(
            '<div data-bind="items">{% for item in component.items %}'
            '<p data-bind="item">{{ item }}</p>{% endfor %}</div>'
        ),
        component=component,
    )
    assert len(rendered.fragments) == 3
    component.items = [3]
    assert len(rendered.refresh("items")) == 1
    assert len(rendered.fragments) == 2
    assert [text for _, text in rendered.refresh("item")] == ["3"]


def test_reactive_defaults_and_assignment_notifications():
    class Counter:
        count = react(0)
        items = react_factory(list)

        def __init__(self):
            self.changes = []

        def invalidate(self, name):
            self.changes.append(name)

    first, second = Counter(), Counter()
    first.items.append(1)
    assert second.items == []
    first.count = 0
    first.count = 1
    assert first.changes == ["count"]


async def test_lifecycle_order_and_undecorated_override_suppression():
    calls = []

    class Base:
        @lifecycle(Lifecycle.BEFORE_INIT)
        def first(self):
            calls.append("base")

        @lifecycle(Lifecycle.BEFORE_INIT)
        def suppressed(self):
            calls.append("bad")

    class Child(Base):
        def suppressed(self):
            pass

        @lifecycle(Lifecycle.BEFORE_INIT)
        async def last(self):
            calls.append("child")

    await run_hooks(Child(), Lifecycle.BEFORE_INIT)
    assert calls == ["base", "child"]


async def test_scope_stops_waiting_for_uncooperative_work():
    scope = Scope()
    started, release = asyncio.Event(), asyncio.Event()

    async def work():
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        return "late"

    waiting = asyncio.create_task(scope.wait(work()))
    await started.wait()
    scope.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(waiting, 0.5)
    release.set()
    await asyncio.sleep(0)


async def test_shared_cache_survives_cancel_and_clear_cannot_repopulate():
    cache = TemplateCache()
    release, started = asyncio.Event(), asyncio.Event()
    calls = []

    async def factory():
        calls.append(1)
        started.set()
        await release.wait()
        return "old"

    first = asyncio.create_task(cache.get("key", 60, factory))
    await started.wait()
    second = asyncio.create_task(cache.get("key", 60, factory))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    cache.clear()
    assert await cache.get("key", 60, lambda: "new") == "new"
    release.set()
    assert await second == "old"
    assert await cache.get("key", 60, factory) == "new"
    assert calls == [1]


async def test_lazy_loaders_share_success_and_retry_failures():
    calls = []

    def factory():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("retry")
        return "loaded"

    dependency = lazy(factory, "test")
    with pytest.raises(RuntimeError, match="test"):
        await dependency.load()
    assert await dependency.preload() == "loaded"
    assert await dependency.load() == "loaded"
    assert len(calls) == 2


class Adapter:
    def query_parameters(self):
        return {}

    def __init__(self):
        self.markups = []

    async def render_component(self, instance, markup, renderer):
        self.markups.append(str(markup))
        instance._renderer = renderer

    async def wait_children(self, instance):
        pass

    def invalidate(self, instance, binding):
        pass


@pytest.mark.parametrize("as_module", [False, True])
async def test_lazy_dependencies_register_components_before_render(as_module):
    registered = []

    @tag("lazy-child")
    class Child(Component):
        pass

    module = ModuleType("test_lazy_widgets")
    Child.__module__ = module.__name__
    module.Child = Child
    dependency = lazy(lambda: module if as_module else Child)

    @tag("lazy-parent")
    class Parent(Component):
        dependencies = [dependency]

        def markup(self):
            assert registered == [Child]
            return template("<lazy-child></lazy-child>")

    app = Application()
    app.adapter = Adapter()
    app.adapter.register_component = registered.append
    instance = Parent(app, None)
    await instance.init_element()
    await instance.dispose()


async def test_initialization_resolves_before_after_init_and_cleanup_once():
    calls = []

    @tag("test-component")
    class Example(Component):
        def markup(self):
            return template("hello")

        @lifecycle(Lifecycle.AFTER_INIT)
        def ready(self):
            assert self.init_complete.done()
            calls.append("ready")

        @lifecycle(Lifecycle.AFTER_DISCONNECT)
        def cleanup(self):
            assert self.scope.closed
            calls.append("cleanup")

    app = Application()
    app.adapter = Adapter()
    instance = Example(app, None)
    await instance.init_element()
    await instance.dispose()
    await instance.dispose()
    assert calls == ["ready", "cleanup"]


async def test_component_render_supersession_and_disconnection():
    started, release = asyncio.Event(), asyncio.Event()

    @tag("test-races")
    class Example(Component):
        slow = False

        async def markup(self):
            if self.slow:
                started.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
                return template("old")
            return template("new")

    app = Application()
    app.adapter = Adapter()
    instance = Example(app, None)
    await instance.init_element()
    instance.slow = True
    pending = asyncio.create_task(instance.rerender())
    await started.wait()
    instance.slow = False
    await instance.rerender()
    await asyncio.wait_for(pending, 0.5)
    release.set()
    await asyncio.sleep(0)
    assert app.adapter.markups == ["new", "new"]
    await instance.dispose()
    with pytest.raises(asyncio.CancelledError):
        await instance.rerender()


async def test_initialization_cause_and_specific_error_dispatch():
    @tag("broken-component")
    class Broken(Component):
        def markup(self):
            raise ValueError("broken")

    app = Application()
    app.adapter = Adapter()
    instance = Broken(app, None)
    with pytest.raises(ElementInitializationError) as captured:
        await instance.init_element()
    assert isinstance(captured.value.__cause__, ValueError)
    assert instance.initialization_error is captured.value
    assert instance.init_complete.exception() is captured.value
    await instance.dispose()


async def test_class_page_auth_chain_and_base_url():
    @auth(["user"])
    @layout
    @tag("main-layout-test")
    class Main(Component):
        pass

    @auth(["editor"])
    @layout
    @tag("sub-layout-test")
    class Sub(Component):
        pass

    @page("/notes/<int:id>", sublayouts=[SubLayout(Sub)])
    @tag("notes-page-test")
    class Notes(Component):
        pass

    class App(Application):
        async def is_authenticated(self):
            return True

        async def check_user_roles(self, roles):
            checked.append(roles)
            return True

    checked = []
    app = App(pages=[Notes], base_layout=Main, base_url="/<str:language>")
    assert await app.navigate("/en/notes/3")
    assert checked == [("user",), ("editor",)]
    assert app.context.params == {"language": "en", "id": 3}
    assert app.url_for("Notes", language="sl", id=4) == "/sl/notes/4"
    await app.stop()


async def test_authorization_failure_and_cause_handlers():
    calls = []

    @auth()
    @page("/")
    @tag("protected-page")
    class Protected(Component):
        pass

    class Errors(ExceptionHandler):
        @handles(AuthenticationError)
        def unauthorized(self, ctx, error):
            calls.append(error)
            return View(markup="login")

    app = Application(pages=[Protected], exception_handlers=[Errors])
    assert await app.navigate("/")
    assert len(calls) == 1
    await app.stop()


async def test_wrapped_error_preserves_navigation_for_cause_handler():
    captured = []

    class Errors(ExceptionHandler):
        @handles(ValueError)
        def invalid(self, ctx, error):
            captured.append(error)

    app = Application(exception_handlers=[Errors])
    cause = ValueError("invalid")
    error = RuntimeError("initialization failed")
    error.__cause__ = cause
    error.__ui_generation__ = 42
    await app.handle_exception(error, None)
    assert captured == [cause]
    assert cause.__ui_generation__ == 42
    await app.stop()


async def test_navigation_preserves_query_changes_during_mount():
    @page("/")
    @tag("query-page")
    class QueryPage(Component):
        pass

    recorded = []

    class Adapter:
        async def present(self, view, context):
            # An input event may run after DOM insertion but before mounting ends.
            context.url = "/?filter=notes"

        def history(self, url, mode):
            recorded.append((url, mode))

        async def close(self):
            pass

    app = Application(pages=[QueryPage])
    app.adapter = Adapter()
    assert await app.navigate("/")
    assert recorded == [("/?filter=notes", "push")]
    assert app.context.query == {"filter": ["notes"]}
    await app.stop()
