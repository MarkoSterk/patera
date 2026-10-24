"""Navigation orchestration with scoped tasks and stale-result protection."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, quote, urlsplit

from .routing import Router
from .view import View, TemplateEngine
from .cache import TemplateCache
from .lifecycle import Lifecycle, run_hooks, Scope
from .metadata import AuthenticationError, AuthorizationError, Page
from .updates import Diagnostics

if TYPE_CHECKING:
    from .browser import APIClient, Browser
    from .components import Component
    from .controller import Controller
    from .exceptions import ExceptionHandler


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@dataclass
class PageContext:
    app: Application
    url: str
    params: dict = field(default_factory=dict)
    _tasks: set = field(default_factory=set)
    _cleanup: list = field(default_factory=list)
    closed: bool = False

    @property
    def query(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.url).query, keep_blank_values=True)

    @property
    def api(self) -> APIClient:
        if self.app.api is None:
            raise RuntimeError("The browser API client is not initialized")
        return self.app.api

    def spawn(self, awaitable: Coroutine[Any, Any, Any]) -> asyncio.Task:
        if self.closed:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise RuntimeError("Page scope is closed")
        task = asyncio.create_task(awaitable)
        self.app.diagnostics.track_task(task)
        self._tasks.add(task)
        task.add_done_callback(self._completed)
        return task

    def _completed(self, task):
        self._tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            if not self.closed:
                self.app.report_error(error, self)

    def on_cleanup(self, callback: Callable) -> None:
        if self.closed:
            raise RuntimeError("Page scope is closed")
        self._cleanup.append(callback)

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for task in tuple(self._tasks):
            # An event is allowed to navigate away from its own page.
            if task is not asyncio.current_task():
                task.cancel()
        for callback in reversed(self._cleanup):
            try:
                await invoke(callback)
            except Exception as error:
                self.app.report_error(error)
        self._cleanup.clear()

    async def navigate(self, url: str, *, history: str = "push") -> bool:
        return await self.app.navigate(url, history=history)


class Application:
    def __init__(
        self,
        import_name: str | None = None,
        *,
        controllers: Iterable[type[Controller]] = (),
        exception_handlers: Iterable[type[ExceptionHandler]] = (),
        components: Iterable[type[Component]] = (),
        templates: dict[str, str] | None = None,
        strict_slashes: bool = False,
        state: Any = None,
        pages=(),
        layouts=(),
        base_layout=None,
        default_target="#page",
        base_url="",
        filters=None,
        globals=None,
        data=None,
        templates_cache_duration=300,
        templates_cache_cleanup_interval=60,
        server_components_url=None,
        batch_updates: bool = False,
        diagnostics: bool = False,
    ) -> None:
        self.batch_updates = batch_updates
        self.diagnostics = Diagnostics(diagnostics)
        if import_name is not None:
            from .components import Component
            from .controller import Controller
            from .discovery import discover
            from .exceptions import ExceptionHandler

            pages = tuple(
                dict.fromkeys((*pages, *discover(import_name, ("pages",), Component)))
            )
            layouts = tuple(
                dict.fromkeys(
                    (*layouts, *discover(import_name, ("layouts",), Component))
                )
            )
            controllers = dict.fromkeys(
                (*controllers, *discover(import_name, ("controllers",), Controller))
            )
            components = dict.fromkeys(
                (*components, *discover(import_name, ("components",), Component))
            )
            exception_handlers = dict.fromkeys(
                (
                    *exception_handlers,
                    *discover(
                        import_name,
                        ("exceptions", "exception_handlers"),
                        ExceptionHandler,
                    ),
                )
            )
        from .components import State

        self.base_layout, self.default_target = base_layout, default_target
        self.base_url = base_url.rstrip("/")
        self.current_route = None
        self.router = Router(strict_slashes)
        self.router.app = self
        self._listeners: dict[str, list] = {}
        self._handled_errors: list[BaseException] = []
        self._error_rendering = False
        self.template_cache = TemplateCache()
        self.templates_cache_duration = templates_cache_duration
        self.templates_cache_cleanup_interval = templates_cache_cleanup_interval
        self.server_components_url = server_components_url
        self.data = State(**(data or {}))
        self.data.subscribe(self._data_changed)
        self.controllers = [controller(self) for controller in controllers]
        for controller in self.controllers:
            for rule, endpoint, handler in controller.routes():
                self.router.add(self.base_url + rule, endpoint, handler)
        self.handlers: dict[type[BaseException], Callable] = {}
        for handler_class in exception_handlers:
            for exception, handler in handler_class(self).mappings():
                if exception in self.handlers:
                    raise ValueError(f"Duplicate handler for {exception.__name__}")
                self.handlers[exception] = handler
        registered = list(
            dict.fromkeys(
                (
                    *components,
                    *pages,
                    *layouts,
                    *((base_layout,) if base_layout else ()),
                )
            )
        )
        for route in self.router.routes:
            options = getattr(route.handler, "__ui_page_options__", None)
            if options:
                for candidate in [
                    options.layout,
                    *(item.layout for item in options.sublayouts),
                ]:
                    if candidate and candidate not in registered:
                        registered.append(candidate)
        for component in list(registered):
            metadata = getattr(component, "__ui_page__", None)
            if metadata:
                self.router.add(
                    self.base_url + metadata.rule,
                    metadata.name or component.__name__,
                    component,
                )
                for candidate in [
                    metadata.layout,
                    *(item.layout for item in metadata.sublayouts),
                ]:
                    if candidate and candidate not in registered:
                        registered.append(candidate)
                for item in metadata.sublayouts:
                    if not getattr(item.layout, "__ui_layout__", False):
                        raise ValueError("Sublayouts must use @layout")
        if base_layout and not getattr(base_layout, "__ui_layout__", False):
            raise ValueError("Base layout must use @layout")
        seen_tags = set()
        for component in registered:
            if not component.tag or component.tag in seen_tags:
                raise ValueError(f"Missing or duplicate component tag: {component.tag}")
            seen_tags.add(component.tag)
        self.components = registered
        self.templates = dict(templates or {})
        self.template_engine = TemplateEngine(
            self.templates, filters=filters, globals=globals
        )
        self.state = state
        self.api: APIClient | None = None
        self.config: dict[str, Any] = {}
        self.adapter: Browser | None = None
        self.context: PageContext | None = None
        self._pending: asyncio.Task | None = None
        self._navigation_scope: Scope | None = None
        self._assets_url = ""
        self._generation = 0
        self._error_tasks: set[asyncio.Task] = set()

    def url_for(self, endpoint: str, **values: Any) -> str:
        relative = self.router.url_for(endpoint, **values)
        return (self.adapter.mount if self.adapter else "") + relative

    def asset_url(self, path: str) -> str:
        if not self._assets_url:
            raise RuntimeError("Application has not started")
        if any(p in {"", ".", ".."} for p in path.split("/")) or "\\" in path:
            raise ValueError("Use a relative frontend asset path")
        return self._assets_url + "/" + quote(path, safe="/")

    async def handle_exception(self, error, context):
        seen = set()
        current = error
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            # Preserve the originating navigation when dispatching a wrapped cause.
            for attribute in ("__ui_generation__", "__ui_context__"):
                if hasattr(error, attribute):
                    setattr(current, attribute, getattr(error, attribute))
            for cls in type(current).__mro__:
                if cls in self.handlers:
                    return await invoke(self.handlers[cls], context, current)
            for cls, handler in self.handlers.items():
                if isinstance(current, cls):
                    return await invoke(handler, context, current)
            current = current.__cause__
        raise error

    def report_error(self, error, context=None):
        if isinstance(error, asyncio.CancelledError) or any(
            error is seen for seen in self._handled_errors
        ):
            return
        self._handled_errors.append(error)
        self._handled_errors = self._handled_errors[-128:]
        context = context or self.context
        generation = self._generation
        setattr(error, "__ui_generation__", generation)
        setattr(error, "__ui_context__", context)

        async def report():
            try:
                result = await self.handle_exception(error, context)
                if (
                    generation == self._generation
                    and isinstance(result, View)
                    and self.adapter
                ):
                    await self.adapter.present(result, context)
            except Exception as unhandled:
                if self.adapter:
                    self.adapter.error(unhandled)
                else:
                    asyncio.get_running_loop().call_exception_handler(
                        {
                            "message": "Unhandled UI error",
                            "exception": unhandled,
                        }
                    )

        task = asyncio.create_task(report())
        self.diagnostics.track_task(task)
        self._error_tasks.add(task)
        task.add_done_callback(self._error_tasks.discard)

    async def navigate(self, url: str, *, history: str = "push") -> bool:
        if history not in {"push", "replace", "none"}:
            raise ValueError("history must be push, replace or none")
        if self.adapter and hasattr(self.adapter, "release_navigation_task"):
            self.adapter.release_navigation_task(asyncio.current_task())
        parsed = urlsplit(url)
        if history != "none" and self.adapter and hasattr(self.adapter, "save_scroll"):
            self.adapter.save_scroll()
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
            raise ValueError("Navigation requires an application-relative URL")
        self._generation += 1
        generation = self._generation
        if self._navigation_scope:
            self._navigation_scope.cancel()
        scope = self._navigation_scope = Scope(diagnostics=self.diagnostics)
        if self._pending:
            self._pending.cancel()
        context = PageContext(self, url)

        async def resolve():
            try:
                route, params = self.router.match(parsed.path)
                context.params = params
                from .components import Component
                from .view import ComponentView

                if isinstance(route.handler, type) and issubclass(
                    route.handler, Component
                ):
                    metadata = route.handler.__ui_page__
                    chain = [
                        metadata.layout or self.base_layout,
                        *(item.layout for item in metadata.sublayouts),
                        route.handler,
                    ]
                    await self.authorize(chain, context)
                    result = ComponentView(route.handler, metadata, context)
                else:
                    metadata = getattr(
                        route.handler, "__ui_page_options__", Page(route.rule)
                    )
                    await self.authorize(
                        [
                            metadata.layout or self.base_layout,
                            *(item.layout for item in metadata.sublayouts),
                            getattr(route.handler, "__self__", None),
                            route.handler,
                        ],
                        context,
                    )
                    result = await invoke(route.handler, context, **params)
                    if isinstance(result, View) and (
                        self.base_layout or metadata.layout or metadata.sublayouts
                    ):
                        result = ComponentView(None, metadata, context, content=result)
                context.route = route
                if not isinstance(result, View):
                    raise TypeError("Page handlers must return a View")
                result.render(self.template_engine)
                return result
            except Exception as error:
                setattr(error, "__ui_generation__", generation)
                setattr(error, "__ui_context__", context)
                return await self.handle_exception(error, context)

        task = self._pending = asyncio.create_task(resolve())
        resolved = False
        try:
            view = await scope.wait(task, shared=True)
            resolved = True
            if generation != self._generation:
                return False
            if not isinstance(view, View):
                raise TypeError("Page handlers must return a View")
            # Validate rendering before replacing the current page.
            view.render(self.template_engine)
            await self.emit("route-start", context)
            if generation != self._generation:
                return False
            if self.context:
                await self.context.close()
            if generation != self._generation:
                return False
            self.context = context
            if self.adapter:
                await scope.wait(self.adapter.present(view, context))
                if generation != self._generation:
                    return False
                self.adapter.history(context.url, history)
            self.current_route = getattr(context, "route", None)
            await self.emit("route-finished", context)
            return True
        except asyncio.CancelledError:
            return False
        except Exception as error:
            if generation == self._generation:
                setattr(error, "__ui_generation__", generation)
                setattr(error, "__ui_context__", context)
                if resolved:
                    try:
                        recovery = await self.handle_exception(error, context)
                        if (
                            isinstance(recovery, View)
                            and self.adapter
                            and generation == self._generation
                        ):
                            await self.adapter.present(recovery, context)
                        return False
                    except Exception as recovery_error:
                        error = recovery_error
                if self.adapter:
                    self.adapter.error(error)
                else:
                    raise error
            return False
        finally:
            if self.context is not context:
                await context.close()
            if self._pending is task:
                self._pending = None

    async def start(self, target: str = "#app", *, config: dict | None = None) -> None:
        if self.adapter is not None:
            raise RuntimeError("Application is already started")
        from .browser import Browser

        self.adapter = Browser(self, target, config or {})
        self.config = dict((config or {}).get("public", {}))
        self._assets_url = (config or {}).get("assets", "")
        self.api = self.adapter.api
        self.server_components_url = self.server_components_url or (config or {}).get(
            "server_components_url"
        )
        try:
            await run_hooks(self, Lifecycle.BEFORE_INIT)
            await run_hooks(self, Lifecycle.EXTENSION_INIT)
            await self.adapter.start()
            if self.templates_cache_cleanup_interval:
                self.adapter.spawn(self._clean_cache())
            await run_hooks(self, Lifecycle.AFTER_INIT)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        self._generation += 1
        if self._navigation_scope:
            self._navigation_scope.cancel()
        if self._pending:
            self._pending.cancel()
        if self.context:
            await self.context.close()
        for task in tuple(self._error_tasks):
            task.cancel()
        if self.adapter:
            await self.adapter.close()
            self.adapter = None
        self.api = None
        self.context = None

    async def flush(self) -> None:
        """Commit queued binding updates, independently of browser frame delivery.

        This is a DOM commit barrier, not a wait for network requests, component
        initialization, event tasks, or a browser paint.
        """
        if self.adapter:
            self.adapter.updates.drain()

    def diagnostics_snapshot(self):
        result = self.diagnostics.snapshot()
        result["resources"] = (
            self.adapter.resources()
            if self.adapter
            else dict(
                components=0,
                tasks=sum(not task.done() for task in self.diagnostics.tasks),
                listeners=0,
                proxies=0,
                subscriptions=len(self.data._subscribers)
                + sum(len(items) for items in self._listeners.values()),
                fragments=0,
                queued_components=0,
            )
        )
        return result

    async def _clean_cache(self):
        while self.adapter:
            delay = self.templates_cache_cleanup_interval
            await asyncio.sleep(delay if delay > 0 else 1)
            if delay > 0:
                self.template_cache.clean()

    def clear_templates_cache(self):
        self.template_cache.clear()

    def clean_templates_cache(self):
        return self.template_cache.clean()

    def on(self, event, callback):
        self._listeners.setdefault(event, []).append(callback)

        def remove():
            if callback in self._listeners[event]:
                self._listeners[event].remove(callback)

        return remove

    async def emit(self, event, *args):
        for listener in tuple(self._listeners.get(event, ())):
            await invoke(listener, *args)

    def _data_changed(self, key, value):
        if self.adapter:
            self.adapter.data_changed(key, value)

    def get_data(self, key, default=None):
        return self.data.get(key, default)

    def set_data(self, key, value):
        self.data[key] = value

    @property
    def query_parameters(self):
        if self.adapter:
            return self.adapter.query_parameters()
        return {
            key: values[-1]
            for key, values in (self.context.query if self.context else {}).items()
        }

    @query_parameters.setter
    def query_parameters(self, values):
        self.update_query_parameters(values, replace_all=True)

    def update_query_parameters(self, values, *, replace_all=False, history="push"):
        if not self.adapter:
            raise RuntimeError("Application has not started")
        self.adapter.update_query(values, replace_all=replace_all, history=history)

    async def is_authenticated(self):
        return False

    async def check_user_roles(self, roles):
        return False

    async def authorize(self, chain, context):
        requirements = [
            getattr(item, "__ui_auth__")
            for item in chain
            if item and hasattr(item, "__ui_auth__")
        ]
        if requirements and not await invoke(self.is_authenticated):
            raise AuthenticationError(context.url)
        for roles in requirements:
            if roles and not await invoke(self.check_user_roles, roles):
                raise AuthorizationError(context.url)

    async def show_error_page(
        self, component, *, error=None, title=None, layout=None, target=None, args=None
    ):
        from .metadata import Page
        from .view import ComponentView

        if (
            error is not None
            and getattr(error, "__ui_generation__", self._generation)
            != self._generation
        ):
            return False
        if self._error_rendering:
            raise RuntimeError("Recursive error-page rendering")
        self._error_rendering = True
        if self._navigation_scope and self._pending is not asyncio.current_task():
            self._navigation_scope.cancel()
        scope = self._navigation_scope = Scope(diagnostics=self.diagnostics)
        self._generation += 1
        generation = self._generation
        if self._pending and self._pending is not asyncio.current_task():
            self._pending.cancel()
        previous = getattr(error, "__ui_context__", None) or self.context
        context = PageContext(self, previous.url if previous else "/")
        if self.context:
            await self.context.close()
        self.context = context
        self.current_route = None
        task = None
        try:
            await self.emit("route-start", context)
            if self.adapter:
                self.adapter.register_component(component)
                task = self._pending = asyncio.create_task(
                    self.adapter.present(
                        ComponentView(
                            component,
                            Page("", title=title, layout=layout, target=target),
                            context,
                            args or {},
                        ),
                        context,
                    )
                )
                await scope.wait(task)
            if generation != self._generation:
                return False
            await self.emit("route-finished", context)
            return True
        except asyncio.CancelledError:
            return False
        finally:
            self._error_rendering = False
            if self._pending is task:
                self._pending = None

    async def fetch_html(self, request, *, scope=None, cache=False, duration=None):
        import json

        if not self.server_components_url or not self.api:
            raise RuntimeError("Configure server_components_url before requesting HTML")

        async def fetch():
            result = await self.api.request(
                "POST", self.server_components_url, data=request, response_type="text"
            )
            if not result.strip():
                raise ValueError("Server component returned empty markup")
            return result

        work = (
            self.template_cache.get(
                json.dumps(request, sort_keys=True),
                self.templates_cache_duration if duration is None else duration,
                fetch,
            )
            if cache
            else fetch()
        )
        return await scope.wait(work) if scope else await work

    async def prefetch_html(self, request, **options):
        return await self.fetch_html(request, cache=True, **options)
