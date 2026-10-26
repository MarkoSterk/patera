# Desktop UI

!!! warning "Experimental"

    This package is not yet ready for production use; its API may change in any release.

`patera-desktop-ui` lets you write the user interface of a [desktop application](../desktop.md)
in Python, using a locally bundled [PyScript](https://pyscript.net) / Pyodide interpreter.

```sh
uv add "patera[desktop-ui]"
```

It requires `patera-desktop>=0.11.2` for namespace and packaging integration.

The backend stays native Python. Browser controllers, components and models run in a separate
interpreter and communicate with Patera HTTP endpoints. Native database sessions, files and
services do not cross that boundary.

This page covers setup, pages, builds and packaging. Layouts, reactive fragments, lifecycle hooks,
authorization and server-rendered components are described in the [runtime guide](runtime.md).

## Application structure

Keep browser sources outside the backend package, so backend discovery and PyInstaller do not
import browser modules:

```text
project/
  app/__init__.py
  app/configs.py
  app/api/notes_api.py
  frontend/
    frontend/__init__.py
    templates/note.html
  ui-runtime/             complete local runtime, including runtime.json
  build/ui/               generated, do not commit
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

## Settings

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

`URL_PREFIX` applies to the shell, assets and API prefixes. Mounts must be disjoint, non-root
paths. Ordinary Patera endpoints outside these prefixes are unchanged.

## Pages

`frontend/frontend/__init__.py`:

```python
from patera.desktop.ui import Application, Controller, PageContext, View, page, path


@path("/notes")
class Notes(Controller):
    @page("/<int:note_id>")
    async def detail(self, ctx: PageContext, note_id: int) -> View:
        note = await ctx.api.get_json(f"/api/notes/{note_id}")
        return View("templates/note.html", note=note, title=note["title"])


app = Application(controllers=[Notes])
```

- Templates use Jinja2 with auto-escaping and strict undefined values; inheritance, includes,
  macros, loops, filters and globals are supported. Use
  `View(markup=html("<h1>{{ title }}</h1>", title=value))` for inline markup, and
  `trusted_html()` only for application-authored markup.
- Interpolate into HTML text or quoted ordinary attributes, never scripts, styles, event-handler
  attributes or unvalidated URLs.
- Routes support `string` (default), non-negative `int` and `path` converters. Trailing slashes
  are ignored by default.
- `app.url_for("Notes.detail", note_id=3, query={"tab": "details"})` includes the mount after
  startup. Several `@page` decorators may alias one method; the first route is used for URL
  generation.
- `ctx.query` maps keys to lists. `ctx.spawn(coroutine)` tracks a task for the page and
  navigation cancels it; `ctx.on_cleanup(callback)` registers resource cleanup.
- Controllers live for the application lifetime; page-local state belongs in the context or in
  components.

`ExceptionHandler` classes with `@handles(ValueError)` methods `(self, ctx, error)` handle page
and event errors; the most specific exception type wins. Return a `View` for an error page, or
`None` from an event handler to keep the current page. Unhandled failures appear in an alert and
the browser console.

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

Register with `Application(..., components=[Counter])` and use `<note-counter></note-counter>` in
a view. `mounted()` and `unmounted()` may be async. Assign to state to notify subscribers;
in-place mutation of nested values does not notify. The newer reactive API (`react`, `data-bind`,
`@click`) is described in the [runtime guide](runtime.md#jinja2-and-reactive-fragments).

## Folder discovery

Use `app = Application(__name__)` in your frontend package's `__init__.py`. The application
recursively imports public modules under `controllers/`, `components/`, `pages/`, `layouts/` and
`exceptions/` (or `exception_handlers/`). Give each folder an `__init__.py`.

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

Concrete subclasses defined in those modules are registered automatically; imported or
re-exported classes are ignored, abstract classes skipped, and import errors surfaced. Explicit
`controllers=`, `components=`, `pages=`, `layouts=` and `exception_handlers=` lists may supplement
discovery.

## Offline runtime and builds

Provision a **complete**, pinned PyScript/Pyodide offline distribution in `ui-runtime`, following
the official [offline guide](https://docs.pyscript.net/2026.7.3/user-guide/offline/). Include
PyScript's supporting modules, the interpreter's `.mjs`, `.js` and `.wasm` files,
`python_stdlib.zip`, `pyodide-lock.json` and the packages the runtime requires, preserving its
layout and licenses. Nothing downloads at application startup.

Record the actual entry paths and versions, then build and run:

```sh
patera cli ui:lock-runtime pyscript/core.js pyscript/pyodide/pyodide.mjs 2026.2.1 0.28.0.dev0 3.13
patera cli ui:build
patera cli desktop:run
```

The tested PyScript **2026.2.1 offline archive** uses these entry paths, with Pyodide
`0.28.0.dev0` and Python `3.13`; extract its `offline/` contents into `ui-runtime/`.

- Commit `runtime.json` or keep it with your build inputs. Every build checks the recorded
  SHA-256 hashes and validates Python syntax against the recorded browser Python version.
- The browser archive contains minimal `patera` / `patera.desktop` parent packages, portable UI
  modules and only allowlisted frontend files. It never installs the native Patera wheel in
  Pyodide.
- The builder excludes hidden files, caches, logs, databases, bytecode and unknown file
  extensions. Frontend Python, HTML, JS, CSS, fonts and images are **public**: keep secrets out
  of the source root.
- Builds are content-addressed and switch `current.json` atomically.

| Command | Purpose |
| --- | --- |
| `ui:build` | build once |
| `ui:watch` | rebuild on changes (in another terminal) |
| `ui:run` | build, watch in a background thread and run the desktop window |
| `ui:run prod` | build and launch without watching |

Development windows (`DEBUG=True`) poll the build version and reload after a successful build;
failed builds keep the working version. Frozen applications never poll or rebuild.

Use `app.config` for `PUBLIC` settings and `app.asset_url("styles.css")` for bundled resources.
Build with the deployment's `URL_PREFIX`.

## Desktop packaging

New `desktop:spec` files include UI asset preparation; both `desktop:package` and direct
`pyinstaller desktop.spec` builds prepare the UI. Existing specs need the `DESKTOP_ASSETS`
setting and the `prepare_desktop_assets` call from a newly generated spec; the package command
rejects old specs when the UI extension is registered. Frozen applications read the artifacts
from PyInstaller's resource directory and never compile sources.

## Local API boundary

Protected API prefixes require `X-Patera-UI-Token` on every HTTP method. The built-in API client
adds it, checks status codes (`APIError`) and aborts fetches when cancelled. Shell and API
requests require a loopback `Host` and reject foreign `Origin` and cross-site fetch metadata.

!!! warning

    This is a browser cross-origin boundary, not authentication against other local processes.
    Backend authorization is still required where applicable. WebSocket routes and native bridges
    are not protected by this middleware. Do not enable permissive CORS for these routes.

## Browser type library

The package includes browser API stubs under `patera.desktop.ui.types` (DOM elements, events,
networking, storage, canvas, media and common JavaScript built-ins) for static analysis:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patera.desktop.ui.types import MouseEvent


def clicked(event: MouseEvent) -> None:
    event.preventDefault()
```

Actual browser objects still come from `js` or `pyscript`.

A complete example lives in
[`examples/desktop_ui_notes`](https://github.com/MarkoSterk/Patera/tree/main/examples/desktop_ui_notes).
