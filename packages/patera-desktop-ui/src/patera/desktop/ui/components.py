"""Component definitions and observable state, with explicit disposal."""

from __future__ import annotations

import re
import asyncio
import json
import inspect
from types import ModuleType
from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypeVar
from .lifecycle import Scope, Lifecycle, invoke, run_hooks
from .metadata import ElementInitializationError
from .view import Template, trusted_html

if TYPE_CHECKING:
    from .application import Application

F = TypeVar("F", bound=Callable[..., Any])
C = TypeVar("C", bound="Component")


def tag(
    name: str,
    *,
    data_field=None,
    group_name="default",
    use_server=False,
    cache=False,
    cache_duration=None,
) -> Callable[[type[C]], type[C]]:
    """Assign a custom-element name without changing the decorated class."""
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", name):
        raise ValueError("Component tags must be lowercase hyphenated names")
    if name in {
        "annotation-xml",
        "color-profile",
        "font-face",
        "font-face-src",
        "font-face-uri",
        "font-face-format",
        "font-face-name",
        "missing-glyph",
    }:
        raise ValueError(f"Reserved custom-element name: {name}")

    def decorate(cls: type[C]) -> type[C]:
        if not issubclass(cls, Component):
            raise TypeError("@tag requires a Component subclass")
        cls.tag = name
        cls.__ui_component__ = dict(
            data_field=data_field,
            group_name=group_name,
            use_server=use_server,
            cache=cache,
            cache_duration=cache_duration,
        )
        return cls

    return decorate


class State:
    def __init__(self, **values: Any) -> None:
        self._values = deepcopy(values)
        self._subscribers: list[Callable[[str, Any], None]] = []

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def get(self, key, default=None):
        return self._values.get(key, default)

    def __setitem__(self, key: str, value: Any) -> None:
        self._values[key] = value
        for callback in tuple(self._subscribers):
            callback(key, value)

    def subscribe(self, callback: Callable[[str, Any], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe():
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe


def event(name: str) -> Callable[[F], F]:
    def decorate(function):
        function.__ui_event__ = name
        return function

    return decorate


class Component:
    """Subclass with a unique hyphenated tag and a render() method.

    Use data-ui-on-click="method", data-ui-text="state_key", and
    data-ui-value="state_key" in component markup. State updates change only
    bound text/value nodes; they do not replace the component's DOM.
    """

    tag = ""
    dependencies = ()
    __ui_component__: dict[str, Any] = {}

    def __init__(self, app: Application, element: Any) -> None:
        self.app = app
        self.element = element
        self.state = State()
        self.args: dict[str, Any] = {}
        self.parent = None
        self.context = app.context
        self.scope = Scope(
            lambda error: app.report_error(error, self.context),
            diagnostics=app.diagnostics,
        )
        self.initialization_state = "pending"
        self.initialization_error = None
        self._init_complete = None
        self._initializing = None
        self._render_scope = None
        self._disposed = False
        self._dispose_complete = asyncio.Event()
        self._disposing_task = None
        self._renderer = None
        self._render_revision = 0

    @property
    def init_complete(self):
        if self._init_complete is None:
            self._init_complete = asyncio.get_running_loop().create_future()
            self._init_complete.add_done_callback(
                lambda f: None if f.cancelled() else f.exception()
            )
        return self._init_complete

    @property
    def metadata(self):
        return getattr(type(self), "__ui_component__", {})

    @property
    def api(self):
        return self.app.api.scoped(self.scope)

    def spawn(self, awaitable):
        return self.scope.spawn(awaitable)

    def on_cleanup(self, callback):
        self.scope.check()
        self.scope.cleanups.append(callback)

    async def init_element(self):
        if self._initializing is None:
            self._initializing = self.app.diagnostics.track_task(
                asyncio.create_task(self._initialize())
            )
        return await self.scope.wait(self._initializing, shared=True)

    async def _initialize(self):
        with self.app.diagnostics.measure("initialization"):
            await self._initialize_element()

    async def _initialize_element(self):
        try:
            for dependency in dict.fromkeys(
                d
                for cls in reversed(type(self).__mro__)
                for d in vars(cls).get("dependencies", ())
            ):
                if hasattr(dependency, "load"):
                    loaded = await self.scope.wait(dependency.load())
                    candidates = (
                        [
                            value
                            for value in vars(loaded).values()
                            if getattr(value, "__module__", None) == loaded.__name__
                        ]
                        if isinstance(loaded, ModuleType)
                        else loaded
                        if isinstance(loaded, (list, tuple))
                        else [loaded]
                    )
                    for candidate in candidates:
                        if (
                            isinstance(candidate, type)
                            and issubclass(candidate, Component)
                            and candidate is not Component
                            and not inspect.isabstract(candidate)
                        ):
                            self.app.adapter.register_component(candidate)
                elif isinstance(dependency, type) and issubclass(dependency, Component):
                    self.app.adapter.register_component(dependency)
                else:
                    raise TypeError(
                        "Component dependencies must be Components or lazy loaders"
                    )
            await run_hooks(self, Lifecycle.BEFORE_INIT, self.scope)
            await self._render(initial=True)
            await self.scope.wait(self.app.adapter.wait_children(self))
            await run_hooks(self, Lifecycle.BEFORE_INIT_RESOLVE, self.scope)
            self.scope.check()
            self.initialization_state = "fulfilled"
            if not self.init_complete.done():
                self.init_complete.set_result(None)
            await run_hooks(self, Lifecycle.AFTER_INIT, self.scope)
            await self.scope.wait(invoke(self.mounted))
        except asyncio.CancelledError:
            if self.initialization_state != "fulfilled":
                self.initialization_state = "cancelled"
            if not self.init_complete.done():
                self.init_complete.cancel()
            raise
        except Exception as cause:
            if self.initialization_state == "fulfilled":
                raise
            error = (
                cause
                if isinstance(cause, ElementInitializationError)
                else ElementInitializationError(self.tag)
            )
            if error is not cause:
                error.__cause__ = cause
            self.initialization_state = "rejected"
            self.initialization_error = error
            if not self.init_complete.done():
                self.init_complete.set_exception(error)
            raise error

    async def _source(self):
        if self.metadata.get("use_server"):
            return trusted_html(await self.fetch_html())
        if type(self).markup is not Component.markup:
            return await invoke(self.markup)
        if type(self).render is not Component.render:
            return await invoke(self.render)
        return None  # Adopt existing DOM without replacing its descendants.

    def template_cache_key(self):
        return json.dumps(
            [
                self.tag,
                self.metadata.get("group_name"),
                self.context.params if self.context else {},
                self.app.query_parameters,
                self.args,
            ],
            sort_keys=True,
            separators=(",", ":"),
        )

    async def _render(self, *, initial=False):
        self.scope.check()
        self._render_revision += 1
        revision = self._render_revision
        if self._render_scope:
            self._render_scope.cancel()
        scope = self._render_scope = Scope(diagnostics=self.app.diagnostics)
        try:
            if not initial:
                await self.scope.wait(
                    scope.wait(run_hooks(self, Lifecycle.BEFORE_RERENDER, scope))
                )
            duration = self.metadata.get("cache_duration")
            duration = (
                self.app.templates_cache_duration if duration is None else duration
            )
            if self.metadata.get("cache") and not self.metadata.get("use_server"):
                source = await self.scope.wait(
                    scope.wait(
                        self.app.template_cache.get(
                            self.template_cache_key(), duration, self._source
                        )
                    )
                )
            else:
                source = await self.scope.wait(scope.wait(self._source()))
            scope.check()
            self.scope.check()
            if isinstance(source, Template):
                with self.app.diagnostics.measure("template"):
                    markup, renderer = self.app.template_engine.render(
                        source,
                        component=self,
                        app=self.app,
                        data=self.app.data,
                        query=self.app.query_parameters,
                        params=self.context.params if self.context else {},
                        args=self.args,
                        ctx=self.context,
                    )
            else:
                markup, renderer = source, None

            async def commit():
                scope.check()
                self.scope.check()
                if revision != self._render_revision:
                    raise asyncio.CancelledError()
                await self.app.adapter.render_component(self, markup, renderer)

            await self.scope.wait(scope.wait(commit()))
            if not initial:
                await self.scope.wait(scope.wait(self.app.adapter.wait_children(self)))
                await self.scope.wait(
                    scope.wait(run_hooks(self, Lifecycle.AFTER_RERENDER, scope))
                )
        except asyncio.CancelledError:
            self.scope.check()
            if not scope.closed:
                raise

    async def rerender(self):
        await self._render()

    async def flush(self):
        """Commit the application's queued binding updates; does not await paint."""
        self.scope.check()
        await self.app.flush()

    async def wait_children(self):
        """Wait for non-deferred child initialization and pending list arg updates."""
        self.scope.check()
        await self.scope.wait(self.app.adapter.wait_children(self))

    def invalidate(self, binding):
        if not self.scope.closed and self.app.adapter:
            self.app.adapter.invalidate(self, binding)

    def select(self, selector):
        return self.app.adapter.select(self, selector)

    def select_all(self, selector):
        return self.app.adapter.select(self, selector, many=True)

    async def insert_html(self, markup, *, target=None, position="beforeend"):
        self.scope.check()
        await self.app.adapter.insert_html(
            self, markup, target=target, position=position
        )

    async def hydrate(self):
        self.scope.check()
        self.app.adapter.hydrate(self)
        await self.app.adapter.wait_children(self)

    async def fetch_html(
        self, *, tag_name=None, group_name=None, args=None, cache=None
    ):
        request = dict(
            tag_name=tag_name or self.tag,
            group_name=group_name or self.metadata.get("group_name", "default"),
            route_parameters=self.context.params if self.context else {},
            query_parameters=self.app.query_parameters,
            attributes=self.args if args is None else args,
        )
        return await self.app.fetch_html(
            request,
            scope=self.scope,
            cache=self.metadata.get("cache", False) if cache is None else cache,
            duration=self.metadata.get("cache_duration"),
        )

    async def dispose(self):
        if self._disposed:
            if asyncio.current_task() is not self._disposing_task:
                await self._dispose_complete.wait()
            return
        self._disposed = True
        self._disposing_task = asyncio.current_task()
        try:
            await self._dispose()
        finally:
            self._renderer = None
            self._disposing_task = None
            self._dispose_complete.set()

    async def _dispose(self):
        self._render_revision += 1
        updates = getattr(self.app.adapter, "updates", None)
        if updates:
            updates.discard(self)
        self.scope.cancel()
        if self._render_scope:
            self._render_scope.cancel()
        if self._initializing and not self._initializing.done():
            self._initializing.cancel()
        if not self.init_complete.done():
            self.init_complete.cancel()
        with self.app.diagnostics.measure("cleanup"):
            try:
                await self.scope.close()
                await run_hooks(self, Lifecycle.AFTER_DISCONNECT)
            finally:
                await invoke(self.unmounted)

    def markup(self):
        return None

    def render(self):
        raise NotImplementedError

    async def mounted(self):
        pass

    async def unmounted(self):
        pass
