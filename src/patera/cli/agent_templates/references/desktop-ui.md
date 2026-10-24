# Desktop UI (experimental)

Install `patera-desktop-ui` alongside `patera-desktop`. Public imports come from
`patera.desktop.ui`; browser type stubs come from `patera.desktop.ui.types`.
Use [desktop](desktop.md) for native windows, configuration, and packaging.
This is a Python/PyScript SPA runtime using Jinja2, not a TypeScript or doT layer.

## Setup and interpreter boundary

Register backend `app_extensions = [Desktop, DesktopUI]`. Configure
`DESKTOP: DesktopConfig = DesktopConfig(INDEX_PAGE="/app/")` and
`DESKTOP_UI: DesktopUIConfig = DesktopUIConfig(...)` on the backend config.
Keep browser sources outside the backend app package:

```text
app/__init__.py              backend app
frontend/frontend/__init__.py  frontend Application instance
frontend/templates/         Jinja .html templates
ui-runtime/                 complete offline runtime plus runtime.json
build/ui/                   generated bundles
```

`DesktopUIConfig` paths are relative to the backend app root. Defaults are
`SOURCE="../frontend"`, `ENTRYPOINT="frontend:app"`, `RUNTIME="../ui-runtime"`,
`OUTPUT="../build/ui"`, `MOUNT="/app"`, `ASSETS="/__ui__"`, `API_PATHS=["/api"]`.
Mounts are disjoint non-root paths; `URL_PREFIX` applies to all three URL groups.
Only explicitly public settings go in `PUBLIC`, exposed as browser `app.config`.

The frontend runs in a separate Pyodide interpreter. Use portable UI imports,
browser APIs, and HTTP calls; native services, files, and database sessions are
not accessible there. The builder bundles minimal namespace parents, portable UI
modules, Jinja2/MarkupSafe, and allowlisted frontend files, not native Patera.
Do not import shared models through a backend package initializer. Frontend
sources/assets are public; keep credentials and backend modules out of them.

## Builds and running

Provision a complete pinned offline PyScript/Pyodide runtime, preserving its
directory structure and licenses. `ui:lock-runtime` takes the PyScript entry,
Pyodide entry, PyScript version, Pyodide version, and Python version, in that
order. Use values from the actual distribution, not guessed/latest versions.
A missing `runtime.json` means provisioning/locking must be completed first.
The manifest records hashes checked on every build. Host Python must be at
least as new as the recorded browser Python for syntax validation.

```sh
patera cli ui:build
patera cli ui:run
patera cli ui:run prod
```

`ui:run` builds, watches in a background thread, and opens the desktop window
on the main thread; closing it stops the watcher and backend. `ui:run prod`
builds and launches without watching. Both require `Desktop`. `ui:watch` is the
standalone watcher. Initial failures prevent launch; later failures retain the
working build. Builds are content-addressed with an atomic `current.json` switch.
Debug windows poll the build version for reload; frozen apps never poll/rebuild.
Do not remove development polling to address application data-fetch behavior.

Both `desktop:package` and direct PyInstaller spec builds prepare UI assets.
Old specs need `DESKTOP_ASSETS` and `prepare_desktop_assets` from a new spec;
retain that preparation in custom specs. Frozen artifacts live under `patera_ui`
in the resource directory. Never compile into the installed application folder.

## Discovery, pages, and layouts

Use `Application(__name__)` in the frontend package initializer to discover
concrete classes defined in public modules under `controllers/`, `components/`,
`pages/`, `layouts/`, and `exceptions/` or `exception_handlers/`. These folders
and nested packages need `__init__.py`. Re-exports are ignored; import failures
surface. This discovery is separate from backend filename conventions.
Explicit registration lists supplement discovery; omit the package name for
explicit-only registration.

- Controller pages: `@path("/notes")` on `Controller`, `@page("/<int:note_id>")`
  on `async def detail(self, ctx: PageContext, note_id: int) -> View`.
- Component pages: `@page("/notes/<int:note_id>")` and `@tag("note-page")` on a
  `Component`; implement `markup()` returning `template(...)` or `Template(...)`.
- Every component has a unique `@tag("custom-element-name")`; do not use a tag
  class attribute. Register explicitly or use folder discovery.
- `@layout` components contain `#page` by default. Set `base_layout` on
  `Application`; use page `layout`, `sublayouts=[SubLayout(..., target=...)]`, and
  `target` for nested outlets. Navigation retains the common layout prefix.

Generate links with `app.url_for(endpoint, **params)` and navigate with
`await app.navigate(url, history="push")` (`replace`/`none` also supported).
Same-origin app links are intercepted; `router-ignore` opts out. Controllers
live for the app lifetime: keep page state in contexts/components.
`PageContext.query` maps keys to lists; `app.query_parameters` holds last values.
Use `query_param` descriptors or `app.update_query_parameters` for URL state.

## Templates, reactivity, and events

Jinja uses autoescape and strict undefined values in both interpreters.
`template(source, **context)` is deferred; `Template(name="templates/x.html")`
loads a named template; `html(...)` renders immediately. Template variables
include `component`, `app`, `data`, `params`, `query`, `args`, and `ctx`.
Use `component.property` explicitly. Only `.html` files become named templates.
`trusted_html` is for trusted markup; server-rendered HTML is never evaluated
again as a browser template.

`react(0)` and `react_factory(list)` descriptors invalidate matching
`data-bind="name"` contents or `{% bind "name" %}...{% endbind %}` blocks.
Assign a new value or call `self.invalidate("name")` after in-place mutation.
Use `app.set_data("notes", value)` for `app.notes` bindings. Full attributes or
structure outside bindings require `await self.rerender()`. Legacy `State`,
`data-ui-text`, and `data-ui-value` remain supported.

Use `@click="method"`/`@input="method"` in markup; these need no event decorator.
Compatibility `data-ui-on-click="method"` requires `@event("click")`. Methods
receive browser event proxies. Submit cancellation is synchronous; use
`data-ui-prevent-default`/`data-ui-stop-propagation` for other events instead of
trying to cancel after an await. `:name='JSON'` or `data-ui-arg-name` supplies
`self.args`. DOM selection and hydration respect child component ownership.

Annotate controller contexts with `PageContext`. Import browser types such as
`MouseEvent`, `InputEvent`, and `HTMLInputElement` under `TYPE_CHECKING`, with
`from __future__ import annotations`; narrow/cast event targets before using
element-specific fields. The stubs are static declarations, not constructors
or wrappers. Runtime objects come from `js`/`pyscript`. There is no separate
`events.py` compatibility module or required webtypy dependency.

## Async work, lifecycle, and API calls

`self.api` is the component's lifetime-bound HTTP client; controller handlers
use `ctx.api`. `await self.api.get_json("/api/notes/3")` fetches backend JSON.
This client adds the UI session token and aborts cancelled fetches; it is not
dependency injection of a native service. Handle `APIError`, `NetworkError`,
and `JsonResponseError` as appropriate.

Use `self.spawn`/`self.on_cleanup` for component-owned tasks/resources and their
`ctx` counterparts for page-owned work. Disconnection/navigation cancels owned
work; obsolete renders/navigation cannot commit. `ElementDisconnectedError`
is cancellation. Use `@lifecycle(Lifecycle.BEFORE_INIT)` to load data before
rendering. `init_complete` resolves after non-deferred children and
`BEFORE_INIT_RESOLVE`, before `AFTER_INIT`/`mounted`. Full rerenders run their
own lifecycle; reactive fragment commits do not run full-render hooks.

`ExceptionHandler` with `@handles(ErrorType)` receives `(self, ctx, error)`;
`ctx` can be `None`. Return a `View` or show an error component with
`app.show_error_page(..., error=error)` to retain navigation provenance.
UI `@auth()`/roles hooks are navigation controls, not backend authorization.
Protected HTTP API prefixes require `X-Patera-UI-Token`; keep loopback/Origin
checks and do not enable permissive CORS. This does not authenticate other local
processes or secure WebSockets/native bridges.

`lazy(...)` dependencies defer execution, not downloading. Markup caching is
opt-in through `@tag(..., cache=True, cache_duration=...)`; invalidate it when
account/permission changes require it. Native `use_server=True` components must
use allowlisted group/tag-to-template mappings via `SERVER_COMPONENTS` or
`register_server_component`, with `SERVER_COMPONENTS_PATH` inside `API_PATHS`.
Never accept arbitrary template paths from request input.

## Update performance and lists

Synchronous binding updates remain the default. Opt into
`Application(..., batch_updates=True)` to coalesce updates on animation frames.
`await self.flush()` or `await app.flush()` commits queued bindings; it does not
wait for paint, network, or event tasks. Use `await self.wait_children()` after
inserting children or changing list child args when their work must complete.

Use keyed blocks to preserve row identity and child state on reorder:

```html
{% keyed "items" %}
  {% for item in component.items %}
    <div data-ui-key="{{ item.id }}">{{ item.title }}</div>
  {% endfor %}
{% endkeyed %}
```

Every direct row needs a stable unique nonempty key and balanced HTML. Keys plus
element types identify retained nodes; changing either replaces the row. Moves
preserve focus/selection and unchanged declared input values retain user edits.
Mounted child interiors belong to the child; changed args schedule its rerender.
Deferred children receive args without automatic initialization. Ordinary nested
bindings work; put nested keyed/virtual lists in separate child components.
Keyed rendering still evaluates all rows.

```html
{% virtual "items", component.items, key="id", row_height=40, height=400, overscan=3 %}
  <span>{{ item.title }}</span>
{% endvirtual %}
```

Virtual blocks supply `item` and zero-based `index`. Keys are attribute/mapping
names or callables returning unique nonempty strings/integers (`1` and `"1"`
collide). Row/viewport heights must be positive, overscan a nonnegative integer.
Use a block container, not table/select markup. Only fixed row heights are
supported. Scroll is frame-coalesced in either update mode; offscreen rows are
disposed. Keep persistent edits/selection outside row-local state; focus is not
pinned when a row leaves the window. Key validation still scans the sequence,
while row template evaluation and mounted DOM are bounded by the viewport.

`diagnostics=True` enables `app.diagnostics_snapshot()` counts/timings and live
resource counts. These are framework metrics, not total WASM memory; nested
timings overlap. Keep diagnostics opt-in and measure cold startup separately
from warm interactions before choosing an optimization.

## Verification and source map

Check portable tests for routing/templates/builds and real-browser tests for
DOM identity, focus, event rebinding, async disposal, and resource stability.
Test both sync/batched updates when changing rendering. Verify fresh-profile
offline startup and a frozen build when changing assets/packaging.

In the framework repository, consult `packages/patera-desktop-ui/README.md`,
`docs/runtime.md` within that package, and its `src/patera/desktop/ui/` modules.
Tests live in `tests/extensions/test_desktop_ui*.py`; browser scenarios are
`tests/browser/desktop_ui.cjs` and `framework_updates.cjs`, with instructions in
`tests/browser/BENCHMARKS.md`. The full SPA example is `examples/desktop_ui_notes`.
These repository paths are source pointers, not assumed files in consumer apps.
