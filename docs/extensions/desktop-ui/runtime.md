# Desktop UI runtime

All runtime imports below come from `patera.desktop.ui`. Browser modules run in Pyodide; native
Patera services remain behind the local HTTP API. Jinja2 is used in both interpreters. Frontend
templates are application code, not a sandbox for untrusted template authors.

## Pages and layouts

```python
from patera.desktop.ui import Application, Component, SubLayout, layout, page, tag, template


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

Every component needs a unique `@tag`. Classes referenced by page layout metadata are registered
automatically.

`@page` accepts `name`, `title`, `layout`, `sublayouts`, `target` and `extras`. A title may be a
sync or async callable receiving the initialized page instance. For nested layouts use
`sublayouts=[SubLayout(DetailLayout, target="#page")]` and `target="#detail-content"` on the page.
Each target is selected inside its owning layout. The default page target is `#page`,
configurable with `Application(default_target=...)`.

Navigation reuses the common prefix of the layout chain, keeping its state and DOM. Pages and
removed layouts are disposed. Layout `params.*` and `query.*` fragments update when route values
change; use `component.context` when a retained layout needs the current page context.

Controller pages remain supported and can use layouts:

```python
from patera.desktop.ui import Controller, PageContext, View, page, path


@path("/notes")
class Notes(Controller):
    @page("/<int:note_id>", layout=MainLayout)
    async def detail(self, ctx: PageContext, note_id: int) -> View:
        note = await ctx.api.get_json(f"/api/notes/{note_id}")
        return View("templates/note.html", note=note)
```

### Routing

- Routes support literal segments, `<name>`, `<str:name>` / `<string:name>`, `<int:name>` and
  `<path:name>`. More specific routes win.
- `base_url` can include parameters, for example `Application(base_url="/<str:language>")`.
- `app.url_for("NotePage", note_id=3)` generates a URL; base parameters must also be supplied
  where required.
- `await app.navigate(url, history="push")` navigates; `history` can also be `replace` or `none`.
  `app.router.redirect(...)` supports `use_base_url` and `base_parameters`.
- Same-origin application links are intercepted unless they have `router-ignore` or the UI
  ignore attribute. Back/Forward restores saved scroll positions. Superseded navigations cannot
  commit stale pages or error pages.

## Jinja2 and reactive fragments

`template(source, **context)` returns a deferred inline template;
`Template(name="templates/note.html", context={...})` loads a named template;
`html(source, **context)` renders immediately. Templates use auto-escaping and strict undefined
values, and support inheritance, includes, macros, loops and custom
`Application(filters={...}, globals={...})`. Only `.html` files are registered as named templates.

Component template variables are `component`, `app`, `data`, `query`, `params`, `args` and `ctx`.
Component properties are accessed explicitly as `component.property`. `trusted_html()` bypasses
escaping; use it only for HTML you trust. Server-rendered HTML is inserted directly and never
interpreted again as a frontend template.

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

- Assigning a reactive property re-renders the **contents** of matching `data-bind` elements;
  the outer element stays in place. Explicit `{% bind "count" %}...{% endbind %}` blocks work
  where a wrapper is unsuitable.
- Bindings keep Jinja loop locals, support nesting and discard stale child bindings. Replaced
  descendant components are disposed and new ones initialized.
- Use `await self.rerender()` when attributes or the whole component must change.
- Mutable defaults are copied per instance; `react_factory(list)` accepts a factory. In-place
  mutations need `self.invalidate("binding")` or assignment of a new value.

### Application data and query parameters

- `app.set_data("notes", notes)` notifies `data-bind="app.notes"` fragments.
  `@tag(..., data_field="notes")` requests a full component re-render when that field changes.
- `query_param("filter", default="")` exposes a URL query value as a descriptor. Assigning it
  updates browser history and `query.filter` bindings.
- `app.update_query_parameters({...}, history="replace")` updates several values; `None` removes a
  key. `app.query_parameters` contains the last value per key; `PageContext.query` preserves
  lists of repeated values.

The earlier `State`, `data-ui-text` and `data-ui-value` APIs remain available.

## Events, arguments and DOM access

Use `@click="method"`, `@input="method"` or `jolt-click="method"` on elements. The compatibility
syntax `data-ui-on-click="method"` requires a matching `@event("click")` decorator. Methods
receive the original browser event proxy.

Submit events are prevented synchronously. Add `data-ui-prevent-default` or
`data-ui-stop-propagation` for other events; calling `preventDefault()` after an `await` is too
late.

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

- Use `:name='JSON'`, `data-jolt-name` or `data-ui-arg-name` attributes to pass component
  arguments through `self.args`. Non-JSON strings stay strings.
- `select()` / `select_all()` respect component ownership: a child host belongs to its parent,
  a child's interior belongs to the child. Selector shorthand `[:name]` works with colon
  attributes.
- `insert_html`, `hydrate` and `fetch_html` integrate dynamically inserted markup with event
  binding and child initialization. Listener proxies are released on replacement.

## Lifecycle and cancellation

Decorate sync or async methods with `@lifecycle(Lifecycle.BEFORE_INIT)` and the other phases:
`EXTENSION_INIT`, `BEFORE_INIT_RESOLVE`, `AFTER_INIT`, `BEFORE_RERENDER`, `AFTER_RERENDER`,
`AFTER_DISCONNECT`. Inherited hooks execute base first; overriding a method suppresses its
inherited registration.

Initialization loads dependencies, runs before-init hooks, renders, waits for child
initialization, runs before-init-resolve hooks, and resolves `init_complete` before after-init
hooks. The `mounted` / `unmounted` hooks are kept. Initialization failures reject with
`ElementInitializationError`, keeping the original error as `__cause__`.

- `self.spawn(coroutine)` and `self.on_cleanup(callback)` bind work and resources to the
  component lifetime; `ctx.spawn` / `ctx.on_cleanup` have the page lifetime.
- `self.api` cancels outstanding requests when the component disconnects.
- `ElementDisconnectedError` is cancellation, not an application failure.
- `dependencies = [OtherComponent, lazy("frontend.widgets.editor")]` registers component
  dependencies and defers imports. This defers execution, not downloading: the offline archive
  contains the source.

## Reactive update scheduling

Existing applications keep synchronous binding updates. Opt into frame batching when
constructing the application:

```python
app = Application(__name__, batch_updates=True, diagnostics=True)

# Inside an async component handler:
self.count += 1                 # Python reads see the new value immediately
self.count += 1
await self.flush()              # or await app.flush()
```

With batching, repeated invalidations of a binding are combined and commits run on the next
animation frame; `flush()` commits immediately, also when the window is hidden. Updates caused
during rendering are handled in later batches, with a 100-batch limit to surface update loops.

`flush()` is a DOM commit barrier for queued bindings, not a paint, network or event-task
barrier. After inserting components through a binding, use `await self.wait_children()` if their
initialization must finish before continuing.

### Diagnostics

With `diagnostics=True`, `app.diagnostics_snapshot()` returns aggregate counts and timings in
milliseconds (template evaluation, DOM replacement, hydration, listeners, initialization and
cleanup) and counts of components, tasks, listeners, subscriptions, fragments and queued
components. `app.diagnostics.reset()` resets measurements. Nested measurements overlap and must
not be summed.

## Keyed lists

Use a Jinja `keyed` block where a `data-bind` loop would otherwise replace every row:

```html
<ul>
  {% keyed "items" %}
    {% for item in component.items %}
      <li data-ui-key="{{ item.id }}">
        <input value="{{ item.title }}">
        <button @click="remove" :item="{{ item.id }}">Remove</button>
      </li>
    {% endfor %}
  {% endkeyed %}
</ul>
```

- Every direct row needs a stable, unique, non-empty `data-ui-key`. Avoid array positions when
  items can move. Missing or duplicate keys fail before DOM reconciliation.
- Matching keys and element types keep their row nodes: changed text and declared attributes are
  patched, rows are created, removed and moved without remounting child components. Input edits,
  focus and selection survive.
- Use balanced HTML; for table rows put the block inside a `<tbody>`.
- Place a nested keyed or virtual list in a child component. Keyed rendering still evaluates the
  whole loop; it reduces DOM and lifecycle churn, not template evaluation.

## Fixed-height virtual lists

For a large sequence, a `virtual` block evaluates and mounts only a visible window plus
overscan:

```html
{% virtual "items", component.items, key="id", row_height=40, height=400, overscan=3 %}
  <span>{{ item.title }}</span>
  <button @click="open" :item="{{ item.id }}">Open</button>
{% endvirtual %}
```

- `key` is a mapping key, attribute name or callable. Keys must be unique non-empty strings or
  integers (integer `1` and string `"1"` collide).
- `row_height` and `height` are positive pixel sizes; `overscan` is a non-negative integer.
  Defaults are 40, 400 and 3. Variable-height rows are not supported.
- Use a normal block container, not a table or select element.
- Off-screen rows are disposed, so keep persistent edits and selection in application state.

## Errors, authorization and application events

`ExceptionHandler` methods decorated with `@handles(ErrorType)` receive `(ctx, error)`. Dispatch
checks the exception's MRO, then compatible registered types, then its cause chain. Methods may
return a `View` or call `await app.show_error_page(ErrorComponent, error=error, args={...})`.
Error pages do not change the current URL.

Use `@auth()` or `@auth(roles=["editor"])` on page and layout classes or controller handlers.
Override `Application.is_authenticated()` and `check_user_roles(roles)` (sync or async). All
applicable layout and page requirements are checked before mounting; failures raise
`AuthenticationError` or `AuthorizationError`.

!!! warning

    These hooks control the UI only. Enforce permissions on the backend as well.

`app.on(name, callback)` returns an unsubscribe function; `await app.emit(name, *args)` awaits
subscribers. Built-in `route-start` and `route-finished` events receive the page context.

## Cached and server-rendered components

`@tag(..., cache=True, cache_duration=30)` caches the markup provider's result for 30 seconds.
The key includes tag, group, route and query parameters and args. Concurrent requests share one
load. `Application(templates_cache_duration=..., templates_cache_cleanup_interval=...)` sets
defaults; `clear_templates_cache()` and `clean_templates_cache()` invalidate entries.

For native rendering, configure the backend explicitly:

```python
DESKTOP_UI = DesktopUIConfig(
    SERVER_COMPONENTS_PATH="/api/ui-components",
    SERVER_COMPONENTS={"default/server-card": "components/card.html"},
)
```

Then declare `@tag("server-card", use_server=True)` on a frontend component. The endpoint must be
inside `API_PATHS`, so the UI session-token guard applies. Only allowlisted group/tag pairs select
templates, which receive the request values as `args`, `query` and `params`.
`DesktopUI.register_server_component(tag, template, group="default", context=callback)` adds
server context; the callback receives `(request, payload)`. Never choose a template path from
request input.

`app.fetch_html` and `app.prefetch_html` use the same rendering and cache path. The API client
supports JSON and text responses, CRUD helpers and cancellation, and distinguishes `APIError`,
`NetworkError` and `JsonResponseError`.

## Compatibility boundaries

This is a Python counterpart of JoltUI, not a TypeScript execution layer. Jinja expressions refer
to Python values; there is no doT engine or JavaScript template evaluation. The packaged browser
runtime targets PyScript/Pyodide on the main thread, not MicroPython or workers. The extension
registers no routes and adds no dependencies to applications that do not use it.
