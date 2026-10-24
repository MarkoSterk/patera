# patera-desktop-ui

Experimental Python UI for `patera-desktop`, using a locally bundled PyScript /
Pyodide interpreter. Install with `pip install patera-desktop-ui`.
Requires `patera-desktop>=0.11.2` for namespace and packaging integration.

The backend stays native Python. Browser controllers, components and models run
in a separate interpreter and communicate with Patera HTTP endpoints. Native
database sessions, files and services do not cross that boundary.

## Application structure

Keep browser sources outside the backend package, so backend discovery and
PyInstaller do not import browser modules:

```text
project/
  app/__init__.py
  app/configs.py
  app/api/notes_api.py
  frontend/
    frontend/__init__.py
    templates/note.html
  ui-runtime/             complete local runtime, including runtime.json
  build/ui/              generated, do not commit
```

```python
from patera import Patera, app
from patera.desktop import Desktop
from patera.desktop.ui import DesktopUI
from .configs import Config

@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Desktop, DesktopUI]
```

```python
from patera import BaseConfig
from patera.desktop import DesktopConfig
from patera.desktop.ui import DesktopUIConfig

class Config(BaseConfig):
    DESKTOP: DesktopConfig = DesktopConfig(INDEX_PAGE="/app/")
    DESKTOP_UI: DesktopUIConfig = DesktopUIConfig(TITLE="Notes")
```

Paths in `DesktopUIConfig` are relative to the backend application's root:

| Setting | Default | Meaning |
| --- | --- | --- |
| `SOURCE` | `../frontend` | Dedicated browser source root |
| `ENTRYPOINT` | `frontend:app` | An `Application` instance; never imported during build |
| `RUNTIME` | `../ui-runtime` | Complete offline runtime and hash manifest |
| `OUTPUT` | `../build/ui` | Build artifacts, outside source/runtime folders |
| `MOUNT` | `/app` | Shell and page URLs |
| `ASSETS` | `/__ui__` | Immutable asset URLs |
| `TITLE` | `Patera` | Initial window document title |
| `PUBLIC` | `{}` | Explicitly public browser configuration |
| `API_PATHS` | `['/api']` | API prefixes requiring the UI session token |

`URL_PREFIX` applies to shell, assets and API prefixes. Mounts must be disjoint,
non-root paths. Ordinary Patera endpoints outside these prefixes are unchanged.

## Pages

`frontend/frontend/__init__.py`:

```python
from patera.desktop.ui import Application, Controller, PageContext, View, path, page

@path("/notes")
class Notes(Controller):
    @page("/<int:note_id>")
    async def detail(self, ctx: PageContext, note_id: int) -> View:
        note = await ctx.api.get_json(f"/api/notes/{note_id}")
        return View("templates/note.html", note=note, title=note["title"])

app = Application(controllers=[Notes])
```

Templates use Jinja2 with autoescaping and strict undefined values. Inheritance,
includes, macros, expressions, loops, filters and globals are supported.
Use `View(markup=html("<h1>{{ title }}</h1>", title=value))` for inline markup.
Use `trusted_html()` only for application-authored markup. Interpolation belongs
in HTML text or quoted ordinary attributes, never scripts, styles, event-handler
attributes or unvalidated URLs. Jinja2 and MarkupSafe's portable Python sources
and licenses are bundled automatically; no browser-side installation is needed.

Component pages, persistent layouts, reactive fragments, lifecycle hooks,
authorization, lazy dependencies and server-rendered components are described
in the [runtime guide](docs/runtime.md). Controller pages remain supported and
can also use layouts.

Routes support `string` (default), nonnegative `int`, and `path` converters.
`app.url_for("Notes.detail", note_id=3, query={"tab": "details"})` includes the
mount after startup. Multiple `@page` decorators may alias one method; the first
registered route is used for URL generation. Distinct handlers cannot share a
route or endpoint. Trailing slashes are ignored by default.

`ctx.query` maps keys to lists. `ctx.spawn(coroutine)` tracks a task for the page;
navigation cancels it. `ctx.on_cleanup(callback)` registers resource cleanup.
Navigation cancels superseded work and checks a generation number before
committing a result. Controllers live for the application lifetime; page-local
state belongs in the context or components.

`ExceptionHandler` with `@handles(ValueError)` methods `(self, ctx, error)` handles
page and event errors; the most specific exception type wins. Return a `View`
for an error page, or `None` from an event handler to retain the current page.
Unhandled failures appear in an alert and the browser console.

## Components

```python
from __future__ import annotations
from typing import TYPE_CHECKING

from patera.desktop.ui import Component, State, event, html, tag

if TYPE_CHECKING:
    from patera.desktop.ui.types import MouseEvent

@tag("note-counter")
class Counter(Component):

    def __init__(self, app, element):
        super().__init__(app, element)
        self.state = State(count=0)

    def render(self):
        return html('<button data-ui-on-click="increment">Count: '
                    '<span data-ui-text="count"></span></button>')

    @event("click")
    def increment(self, event: MouseEvent) -> None:
        self.state["count"] += 1
```

Register with `Application(..., components=[Counter])`; use
`<note-counter></note-counter>` in a view. `mounted()` and `unmounted()` may be
async. Event names are explicit; `data-ui-on-input="change"` requires
`@event("input")`. `data-ui-value` updates a control's value; use an input handler
to write back to state. Bindings update nodes without replacing the component,
preserving input focus. Assign to state to notify subscribers; in-place mutation
of nested values does not notify. `State.subscribe()` returns an unsubscribe
function. The runtime owns and releases DOM listener proxies.

## Offline runtime and builds

Provision a **complete** pinned PyScript/Pyodide offline distribution in
`ui-runtime`. Follow the official [offline guide](https://docs.pyscript.net/2026.7.3/user-guide/offline/).
Include PyScript's supporting modules, the interpreter's `.mjs`, `.js`, `.wasm`,
`python_stdlib.zip`, `pyodide-lock.json`, and packages required by that runtime.
Preserve its directory layout and licenses. Nothing downloads at application
startup or as a side effect of extension registration.

Record the actual entry paths and versions (these arguments describe your
chosen runtime; do not substitute a different version's files):

```sh
patera cli ui:lock-runtime pyscript/core.js pyscript/pyodide/pyodide.mjs 2026.2.1 0.28.0.dev0 3.13
patera cli ui:build
patera cli desktop:run
```

The tested PyScript **2026.2.1 offline archive** uses entry paths
`pyscript/core.js` and `pyscript/pyodide/pyodide.mjs`, with Pyodide
`0.28.0.dev0` and Python `3.13`. For that archive, extract its `offline/`
contents into `ui-runtime/` and use the command above.

Other releases can require a newer host Python for syntax validation. The
runtime is an explicit build input rather than a floating CDN dependency.

Commit `runtime.json` or retain it with your build inputs. Every build checks
the recorded SHA-256 hashes. The builder validates Python syntax against the
recorded browser Python version; build with a host Python at least that new.
This does not validate third-party package compatibility or ensure an incomplete
runtime has all of its transitive assets: test a fresh browser profile offline.

The browser archive contains minimal `patera`/`patera.desktop` parent packages,
portable UI modules, and only allowlisted frontend files. It never installs the
native Patera wheel in Pyodide. Thus public UI imports stay the same without
changing Patera core imports. Frontend packages need `__init__.py`; their parent
initializers must be browser-safe. Keep shared models in a separate lightweight
package rather than importing through the backend application's initializer.

The builder excludes hidden files, caches, logs, databases, bytecode and unknown
file extensions. Frontend Python, HTML, JS, CSS, fonts and images are public.
Do not put secrets in this source root. `.html` files become named templates;
other non-Python assets are served below the build's `public/` URL.

Builds are content-addressed and switch `current.json` atomically. Re-run
`ui:build` after edits, or run `patera cli ui:watch` in another terminal.
For a single-command desktop workflow, use `patera cli ui:run`: it builds first,
watches in a background thread, and runs the desktop window on the main thread.
Closing the window or Ctrl+C stops the watcher; any active build finishes before
exit. The desktop extension handles backend shutdown. Initial build failures
prevent launch; subsequent failures retain the working build. `ui:run prod`
builds and launches without watching. Both modes require the Desktop extension.
Development windows (`DEBUG=True`) poll the build version and reload after a
successful build. Failed builds preserve the working version. Previous builds
remain available to already-open windows. Frozen applications never poll or
rebuild. Third-party dependency installation is not included in this version.

Use `app.config` for `PUBLIC` settings and `app.asset_url("styles.css")` for
bundled non-template resources after startup. Build with the deployment's
`URL_PREFIX`; the generated interpreter configuration contains that prefix.

## Desktop packaging

New `desktop:spec` files include extension asset preparation. Both
`desktop:package` and direct `pyinstaller desktop.spec` builds prepare the UI.
Existing specs need the `DESKTOP_ASSETS` setting and `prepare_desktop_assets`
call from a newly generated spec. The package command rejects old specs when
the UI extension is registered. Custom specs must retain this call.

Artifacts are installed under `patera_ui` in PyInstaller's resource directory.
Frozen applications read those artifacts, never compile sources or write to
the installation directory. Runtime configuration is separate from the bundle;
the API session token is generated per backend process and never persisted.

## Local API boundary

Protected API prefixes require `X-Patera-UI-Token` on every HTTP method. The
built-in API client adds it, checks status codes (`APIError`), and aborts fetches
when cancelled. Shell/API requests require a loopback Host and reject foreign
Origin and cross-site fetch metadata. This works with both the development
subprocess and packaged server thread because the shell obtains the token from
the running server. Do not enable permissive CORS for these routes.

This is a browser cross-origin boundary, not authentication against other local
processes. Backend authorization is still required where applicable. WebSocket
routes and native bridges are not provided or protected by this HTTP middleware;
secure them independently. Keep heavy computation on the backend. The initial
browser adapter targets Pyodide on the main thread, not MicroPython or workers.

## Verification

`pytest tests/extensions/test_desktop_ui.py` covers portable routing, escaping,
cancellation, deterministic builds, runtime hashes, native-import isolation,
HTTP serving, API protection, frozen paths, and standalone spec execution.

The optional `tests/browser/desktop_ui.cjs` Playwright test exercises the notes
example in a fresh browser context with all non-local requests blocked. It
checks saving, escaped text, navigation, Back/Forward and deep-link refresh.
Install Playwright separately; set `NODE_PATH` to its node_modules folder and
`UI_TEST_URL` to the running example's `/app/` URL. `UI_TEST_BROWSER=msedge`
uses installed Edge instead of Playwright's Chromium. Run with
`node tests/browser/desktop_ui.cjs`. No browser automation dependency is added
to the framework's runtime dependencies.

### Folder discovery and type hints

Use `app = Application(__name__)` in your frontend package's `__init__.py`.
The application recursively imports public modules under `controllers/`,
`components/`, `pages/`, `layouts/`, and `exceptions/` (or `exception_handlers/`). Give each folder
an `__init__.py`; nested packages work too, including inside the browser ZIP.
Concrete subclasses defined in those modules are registered automatically.
Imported/re-exported classes are ignored, abstract classes are skipped, and
import errors are surfaced. Modules are visited in deterministic name order.
Only these frontend folders are scanned; backend discovery is unchanged.

```text
frontend/
  __init__.py              # app = Application(__name__)
  controllers/
    __init__.py
    pages.py               # @path class Pages(Controller), @page methods
  components/
    __init__.py
    counter.py             # @tag("note-counter") class Counter(Component)
  exceptions/
    __init__.py
    errors.py              # class Errors(ExceptionHandler), @handles methods
```

Explicit `controllers=`, `components=`, `pages=`, `layouts=`, and `exception_handlers=` lists may
supplement discovery; the same class is registered once. Omit the package name
to use only explicit registration. Use `@tag("note-counter")` on each component.

Import `PageContext` to annotate page handlers as
`async def index(self, ctx: PageContext) -> View`. Error handlers may receive
`PageContext | None` when no page is active. For event handlers, import `Event`,
`MouseEvent`, `KeyboardEvent`, `InputEvent`, or `SubmitEvent` from
`patera.desktop.ui.types` under `TYPE_CHECKING`, with postponed annotations.
These stubs describe the original browser event proxy; they do not wrap or
convert events. Narrow or cast event targets to access element-specific fields.

## Reactive update scheduling and diagnostics

Existing applications keep synchronous binding updates. Opt into frame batching
when constructing the frontend application:

```python
app = Application(__name__, batch_updates=True, diagnostics=True)

# Inside an async component handler:
self.count += 1                 # Python reads see the new value immediately
self.count += 1
await self.flush()               # or await app.flush()
```

With batching, repeated invalidations of a binding are combined. A selected
parent fragment also covers its selected descendants. Normal commits run on the
next animation frame; explicit `flush()` commits without waiting for a frame,
including when the window is hidden. Updates caused during rendering are handled
in subsequent batches, with a 100-batch limit to surface update loops. Disposing a
component removes its queued work. Full `rerender()` remains an explicit async
operation; batching applies to reactive binding/text/value updates.

`flush()` is a DOM commit barrier for queued bindings, not a paint, network,
initialization, or event-task barrier. After inserting components through a
binding, use `await self.wait_children()` if their initialization must
finish before continuing. `insert_html()` and `hydrate()` already wait for
non-deferred children. Initial rendering resolves `init_complete` after those
children and `BEFORE_INIT_RESOLVE`; `AFTER_INIT` and `mounted()` run afterward.
Explicit `rerender()` waits for children before `AFTER_RERENDER`. Fragment updates
do not invoke full-render lifecycle hooks. A newer render or disposal prevents
obsolete asynchronous results from committing.

Fragment commits retain listeners outside the replaced subtree, hydrate only
inserted nodes, and skip identical output. Binding identifiers remain stable
when an unchanged parent recreates its nested bindings. Form submission and
explicit event modifiers still cancel events during synchronous DOM dispatch.
Ordinary list bindings still replace their rendered range. Use the opt-in list
blocks below for keyed reconciliation or virtualization.

Diagnostics are disabled by default. With `diagnostics=True`, inspect
`app.diagnostics_snapshot()` for aggregate counts and timings in milliseconds:
template evaluation, DOM replacement, hydration, listener addition/removal,
initialization, and cleanup. Initialization/cleanup timings include awaited work;
nested measurements overlap and must not be summed as a total. The snapshot also
counts registered components, component/browser tasks, listeners/proxies,
subscriptions, fragments, and queued components. These are framework resource
counts, not total Python/WebAssembly memory or arbitrary user-created tasks.
`app.diagnostics.reset()` resets measurements without changing live resources.
Snapshots contain copied numeric data, not retained component/event references.

See `tests/browser/framework_updates.cjs` for isolated framework workloads and
`tests/browser/BENCHMARKS.md` for running the browser checks and comparisons.

## Keyed lists

Use a Jinja `keyed` block where a `data-bind` loop would otherwise replace every
row. The block name is the invalidation name, just like a normal binding:

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

For example, an `items = react_factory(list)` field invalidates this block on
assignment. Every direct row needs a stable, unique, non-empty `data-ui-key`.
Keys describe item identity, so avoid array positions when items can move.
Missing/duplicate keys and malformed row HTML fail before DOM reconciliation.
Use explicitly balanced HTML; for table rows put the block inside a `<tbody>`.

Matching keys and element types retain their row nodes. The framework patches
changed text and declared attributes, creates new rows, removes obsolete rows,
and moves existing rows without remounting their Patera child components. Input
edits remain intact when their declared value did not change; an explicitly
changed value updates the field. Focus and selection survive moves of retained
elements. Event handlers are rebound only where their declarations changed.

A mounted child component owns its interior. Its host and local Python state
survive a move; changed `:argument`/`data-ui-arg-*` values update `args` and schedule
its normal `rerender()` lifecycle. After `await self.flush()`, use
`await self.wait_children()` to await new child initialization and pending list
argument updates. Removed children are disposed. Changing a row's key or element
type deliberately replaces it. Deferred children receive new arguments without
being initialized automatically. These guarantees cover framework-controlled moves
within the list, not arbitrary DOM moves across component/application owners.

Nested ordinary `bind`/`data-bind` regions inside rows are supported. Place a
nested keyed or virtual list in a child Component so it has its own renderer and
lifetime. Keyed rendering still evaluates the entire loop; it reduces DOM and
lifecycle churn, rather than the amount of row-template evaluation.

## Fixed-height virtual lists

For a large sequence, a `virtual` block evaluates and mounts only a visible
window plus overscan. Its body receives `item` and zero-based `index`:

```html
{% virtual "items", component.items, key="id", row_height=40, height=400, overscan=3 %}
  <span>{{ item.title }}</span>
  <button @click="open" :item="{{ item.id }}">Open</button>
{% endvirtual %}
```

`key` is a mapping key, object attribute name, or callable such as
`key=component.item_key`. Key values must be non-empty strings or integers and
must be unique across the sequence (integer `1` and string `"1"` collide).
`row_height` and viewport `height` are positive pixel sizes; `overscan` is a
non-negative integer. Defaults are 40, 400, and 3 respectively. The framework
provides a scroll viewport, spacer elements, fixed-height row wrappers, and
list/listitem roles with position and total-size attributes. Keep row content
within the configured height; variable-height rows and automatic measurement
are not supported. Use a normal block container, not a table or select element.

Scroll updates are frame-coalesced in either application update mode, and a
scroll that stays within the same rendered window does not reevaluate templates.
The viewport and overlapping keyed rows retain identity. Filtering clamps the
scroll offset when the sequence shrinks; empty sequences remove all rows.
Off-screen rows are disposed, so keep persistent edits/selection in application
state rather than solely in a row component. Keyboard focus on a row removed
from the window is not pinned or restored automatically.

The items expression and keys are reevaluated on invalidation; key validation
still scans the sequence. Only row-template evaluation, DOM size, and mounted
row components are bounded by the viewport. These APIs add no frontend runtime
dependencies and keep Jinja2 as the template engine.

## Browser type library

The package includes a broad browser API stub library under
`patera.desktop.ui.types`, covering DOM elements, events, networking, storage,
canvas, media and common JavaScript built-ins. No webtypy dependency is needed.

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patera.desktop.ui.types import MouseEvent, HTMLInputElement

def clicked(event: MouseEvent) -> None:
    event.preventDefault()
    button: int = event.button
```

These declarations are for static analysis; actual browser objects still come
from `js` or `pyscript`. See the [type library guide](src/patera/desktop/ui/types/README.md)
for coverage and limitations and [provenance](src/patera/desktop/ui/types/NOTICE.md)
for the generated definitions' MPL-2.0 license.
