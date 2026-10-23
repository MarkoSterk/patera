# Browser and JavaScript types

These development-only stubs ship with `patera-desktop-ui`. Mypy and Pylance
discover them through the package's `py.typed` marker; no `MYPYPATH`, replacement
`js` package, or webtypy installation is required.

```python
from __future__ import annotations
from typing import TYPE_CHECKING, cast
from patera.desktop.ui import Component, event, tag

if TYPE_CHECKING:
    from patera.desktop.ui.types import MouseEvent, HTMLInputElement

@tag("note-counter")
class Counter(Component):
    @event("click")
    def increment(self, event: MouseEvent) -> None:
        event.preventDefault()
        button: int = event.button
        field = cast("HTMLInputElement", self.element.querySelector("input"))
        self.state["value"] = field.value
```

Import actual browser objects from `js` or `pyscript` at runtime. This package
contains annotations, not JS implementations or runtime constructors. Use
`TYPE_CHECKING` and postponed annotations, including in native Python tests.
Do not call `get_type_hints()` on these annotations without supplying their
names; the declarations intentionally do not exist at runtime.

## Coverage and limitations

The generated snapshot includes 1,860 interfaces and dictionaries: DOM and
HTML elements, events, CSS, SVG, Fetch, WebSocket, storage, IndexedDB, canvas,
WebGL, audio/video, observers, workers, permissions and other browser APIs.
The original supplement includes arrays, maps, sets, promises, dates, regular
expressions, JSON, buffers, data views and typed arrays. JavaScript primitive
values cross the Pyodide boundary as Python `str`, `bool`, `int` or `float`.

This is a broad browser API snapshot, not a promise of every JS API ever made.
Node.js, third-party libraries, vendor-specific globals and APIs added after
the upstream snapshot are outside its coverage. Some uncommon callback
signatures remain `Callable[..., Any]`, and dynamically shaped values such as
JSON remain `Any`. ECMAScript built-ins are a practical subset, not exhaustive.
Missing members are reported rather than accepted through a blanket `Any`.
DOM availability still depends on the webview version and execution context.

Targets are `EventTarget | None`; use a checked narrowing or explicit cast for
element-specific properties. JavaScript constructors use `.new(...)` through
Pyodide. Import event annotations from this subpackage under `TYPE_CHECKING`;
the main `patera.desktop.ui` package does not export event types.

See `NOTICE.md` for provenance, regeneration and the MPL-2.0 license applying
to the generated browser definitions. The supplement is Patera's original code.
