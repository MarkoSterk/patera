# Python UI runtime

All runtime imports below come from `patera.desktop.ui`. Browser modules run in
Pyodide; native Patera services remain behind the local HTTP API. Jinja2 is used
in both interpreters. Frontend templates are application code, not a sandbox for
untrusted template authors.

## Pages and layouts

```python
from patera.desktop.ui import (
    Application, Component, SubLayout, layout, page, tag, template,
)

@layout
@tag("main-layout")
class MainLayout(Component):
    def markup(self):
        return template('<header>My application</header><main id="page"></main>')

@page("/notes/<int:note_id>", title="Note")
@tag("note-page")
class NotePage(Component):
    def markup(self):
        return template('<h1>Note {{ params.note_id }}</h1>')

app = Application(__name__, base_layout=MainLayout)
```

Discovery scans `pages/`, `layouts/`, `components/`, `controllers/`, and
`exceptions/` (or `exception_handlers/`). Modules must be in Python packages.
Alternatively pass explicit `pages`, `layouts`, `components`, `controllers`,
and `exception_handlers` lists. Classes referenced by page layout metadata are
registered automatically. Every component needs a unique `@tag`.

`@page` accepts `name`, `title`, `layout`, `sublayouts`, `target`, and `extras`.
A title may be a sync/async callable receiving the initialized page instance.
For nested layouts use `sublayouts=[SubLayout(DetailLayout, target="#page")]`
and `target="#detail-content"` on the page. Each target is selected inside its
owning layout. The default page target is `#page`, configurable with
`Application(default_target=...)`.

Navigation reuses the common prefix of the layout chain, retaining its state
and DOM. Pages and removed layouts are disposed. Layout `params.*` and
`query.*` fragments update when route values change; use `component.context`
when a retained layout needs the current page context.

Controller pages remain supported:

```python
from patera.desktop.ui import Controller, PageContext, View, path, page

@path("/notes")
class Notes(Controller):
    @page("/<int:note_id>", layout=MainLayout)
    async def detail(self, ctx: PageContext, note_id: int) -> View:
        note = await ctx.api.get_json(f"/api/notes/{note_id}")
        return View("templates/note.html", note=note)
```

Routes support literal segments, `<name>`, `<str:name>`/`<string:name>`,
`<int:name>`, and `<path:name>`. More specific routes win. `base_url` can include
parameters, for example `Application(base_url="/<str:language>")`.
`app.url_for("NotePage", note_id=3)` generates a URL; base parameters must also
be supplied where required. `await app.navigate(url, history="push")` navigates;
history can also be `replace` or `none`. `app.router.redirect(...)` supports
`use_base_url` and `base_parameters`. Same-origin application links are
intercepted unless they have `router-ignore` or the existing UI ignore attribute.
Back/Forward restores saved scroll positions. Superseded navigations cannot
commit stale pages or error pages.

## Jinja2 and reactive fragments

`template(source, **context)` returns a deferred inline template;
`Template(name="templates/note.html", context={...})` loads a named template.
`html(source, **context)` renders immediately. Templates use autoescaping and
strict undefined values. Inheritance, includes, macros, loops and custom
`Application(filters={...}, globals={...})` are supported. Only `.html` files
are registered as named templates by the builder.

Component template variables include `component`, `app`, `data`, `query`,
`params`, `args`, and `ctx`. Component properties are accessed explicitly as
`component.property`. `trusted_html()` bypasses escaping; only use it for HTML
you intend to trust. Server-rendered HTML is inserted directly and is never
interpreted a second time as a frontend Jinja template.

```python
from patera.desktop.ui import Component, react, tag, template

@tag("note-counter")
class Counter(Component):
    count = react(0)

    def markup(self):
        return template('''
          <button @click="increment">Increment</button>
          <span data-bind="count">{{ component.count }}</span>
        ''')

    def increment(self, event):
        self.count += 1
```

Assigning a reactive property rerenders the **contents** of matching
`data-bind` elements. The outer element remains in place. Explicit
`{% bind "count" %}...{% endbind %}` blocks work where a wrapper is unsuitable.
Bindings preserve Jinja loop locals, support nesting, and discard stale child
bindings. Replaced descendant components are disposed and new ones initialized.
Use `await self.rerender()` when attributes or the whole component must change.
Mutable defaults are copied per instance; `react_factory(list)` accepts a
factory. In-place mutations require `self.invalidate("binding")` or assignment
of a new value.

`app.set_data("notes", notes)` notifies `data-bind="app.notes"` fragments.
`@tag(..., data_field="notes")` requests a full component rerender when that
application field changes. `query_param("filter", default="")` exposes a URL
query value as a descriptor. Assigning it updates browser history and
`query.filter` bindings. `app.update_query_parameters({...}, history="replace")`
can update several values; `None` removes a key. `app.query_parameters` contains
the last value per key; `PageContext.query` preserves lists of repeated values.

The earlier `State`, `data-ui-text`, and `data-ui-value` APIs remain available.

## Events, arguments, and DOM access

Use `@click="method"`, `@input="method"`, or `jolt-click="method"` on elements.
The compatibility syntax `data-ui-on-click="method"` requires a matching
`@event("click")` decorator. Methods receive the original browser event proxy.
Submit events are prevented synchronously. Add `data-ui-prevent-default` or
`data-ui-stop-propagation` when that behavior is needed for other events;
calling `preventDefault()` after an `await` is too late.

```python
from __future__ import annotations
from typing import TYPE_CHECKING, cast
from patera.desktop.ui import select

if TYPE_CHECKING:
    from patera.desktop.ui.types import HTMLInputElement, InputEvent

# Inside a Component:
title_input = select('input[name="title"]', required=True)

def changed(self, event: InputEvent) -> None:
    value = cast("HTMLInputElement", event.target).value
```

Use `:name='JSON'`, `data-jolt-name`, or `data-ui-arg-name` attributes to pass
component arguments through `self.args`. Non-JSON strings remain strings.
`select()`/`select_all()` descriptors and methods respect component ownership:
a child host belongs to its parent, while a child's interior belongs to the
child. Selector shorthand `[:name]` works with colon attributes.
`insert_html`, `hydrate`, and `fetch_html` integrate dynamically inserted markup
with event binding and child initialization. Listener proxies are released on
replacement/disconnection.

## Lifecycle and cancellation

Decorate sync or async methods with `@lifecycle(Lifecycle.BEFORE_INIT)` and the
other phases: `EXTENSION_INIT`, `BEFORE_INIT_RESOLVE`, `AFTER_INIT`,
`BEFORE_RERENDER`, `AFTER_RERENDER`, `AFTER_DISCONNECT`. Inherited hooks execute
base first; overriding a method suppresses its inherited registration.

Initialization loads dependencies, runs before-init hooks, renders, waits for
child initialization, runs before-init-resolve hooks, and resolves
`init_complete` before after-init hooks. Legacy `mounted`/`unmounted` hooks are
retained. Initialization failures reject the future with
`ElementInitializationError`, retaining the original error as `__cause__`.

`self.spawn(coroutine)` and `self.on_cleanup(callback)` bind work and resources
to the component lifetime. `self.api` cancels outstanding requests when the
component disconnects. `ctx.spawn`/`ctx.on_cleanup` have the page lifetime.
Rerenders cancel obsolete render waits; disconnection interrupts initialization
and rendering. `ElementDisconnectedError` is cancellation, not an application
failure. Shared dependency/template work survives cancellation of one waiter.

`dependencies = [OtherComponent, lazy("frontend.widgets.editor")]` registers
component dependencies and defers imports. `lazy` also accepts a sync or async
loader. Successful loads are shared; failures may be retried. This defers
execution, **not** downloading: the offline archive contains the source.

## Errors, authorization, and application events

`ExceptionHandler` methods decorated with `@handles(ErrorType)` receive
`(ctx, error)`. Dispatch checks the exception's MRO, then compatible registered
types, then its cause chain. Methods may return a `View` or call
`await app.show_error_page(ErrorComponent, error=error, args={...})`. Error pages
do not change the current URL. Passing the error preserves its originating
navigation, so a delayed handler cannot replace a newer page.

Use `@auth()` or `@auth(roles=["editor"])` on page/layout classes or controller
handlers. Override `Application.is_authenticated()` and `check_user_roles(roles)`
with sync/async methods. All applicable layout and page requirements are checked
before mounting. These hooks control the UI; enforce permissions on the backend
as well. Failures raise `AuthenticationError` or `AuthorizationError`.

`app.on(name, callback)` returns an unsubscribe function;
`await app.emit(name, *args)` awaits subscribers. Built-in `route-start` and
`route-finished` events receive the page context. Application startup also runs
decorated `BEFORE_INIT`, `EXTENSION_INIT`, and `AFTER_INIT` lifecycle hooks.

## Cached and server-rendered components

`@tag(..., cache=True, cache_duration=30)` caches the markup provider's result
for 30 seconds. The key includes tag, group, route/query parameters and args.
Local Jinja rendering still happens per instance. Concurrent requests share one
load. `Application(templates_cache_duration=..., templates_cache_cleanup_interval=...)`
sets defaults. `clear_templates_cache()` invalidates pending results as well as
stored entries; `clean_templates_cache()` removes expired entries. Clear caches
when application-specific account or permission changes require it.

For native rendering, configure the backend explicitly:

```python
DESKTOP_UI = DesktopUIConfig(
    SERVER_COMPONENTS_PATH="/api/ui-components",
    SERVER_COMPONENTS={"default/server-card": "components/card.html"},
)
```

Then declare `@tag("server-card", use_server=True)` on a frontend component.
The endpoint must be inside `API_PATHS`, so the normal UI session-token guard
applies. Requests contain `group_name`, `tag_name`, `attributes`,
`query_parameters`, and `route_parameters`; only
allowlisted group/tag pairs select templates. Native templates receive those
values as `args`, `query`, and `params`. `DesktopUI.register_server_component(tag, template, group="default",
context=callback)` allows additional server context; the sync/async callback
receives `(request, payload)`. Never choose a template path from request input.

`app.fetch_html` and `app.prefetch_html` expose the same rendering/cache path.
The API client supports JSON and text responses, CRUD helpers, cancellation,
and distinguishes `APIError`, `NetworkError`, and `JsonResponseError`.

## Compatibility boundaries

This is a Python counterpart of JoltUI, not a TypeScript execution layer.
Jinja expressions refer to Python values; there is no doT engine or JavaScript
template evaluation. Decorators and method names use Python conventions.
The packaged browser runtime targets PyScript/Pyodide on the main thread.
The optional extension does not register routes or add dependencies to ordinary
Patera applications that do not install/use it.
