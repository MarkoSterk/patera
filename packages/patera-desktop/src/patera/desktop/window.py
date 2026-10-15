"""
The desktop window: pywebview's options from the DESKTOP settings, and the
window's size and position, remembered between starts.

The window reports moves and resizes as events; GeometryTracker follows
them and keeps the last "normal" geometry, the one to restore at the next
start. Only the user's changes count:

- Changes reported while the window is being placed, until shortly after
  it is shown, are ignored. Some toolkits report a slightly different
  position than the one they were given (Qt by a frame's width), which
  would otherwise move the window a little at every start.
- A maximized or minimized window does not change it. The toolkits report
  the resize and move that come with maximizing before or after the
  maximize itself, so the tracker undoes changes reported just before it.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence

if TYPE_CHECKING:
    from .desktop import DesktopConfig

#: File in the user's data folder with the window's last size and position.
GEOMETRY_FILE_NAME = "window.json"
#: Folder in the user's data folder for the web view's cookies and storage.
STORAGE_FOLDER_NAME = "webview"

# Changes reported this many seconds before a maximize belong to it.
_MAXIMIZE_SECONDS = 0.5
# Changes reported until this many seconds after the window is shown belong
# to placing it.
_SETTLE_SECONDS = 1.0
# How much of a remembered window must be on a screen to be reachable.
_VISIBLE_WIDTH, _VISIBLE_HEIGHT = 100, 50


@dataclass(frozen=True)
class WindowGeometry:
    width: int
    height: int
    x: Optional[int] = None  # None: centered
    y: Optional[int] = None
    maximized: bool = False


def default_geometry(configs: "DesktopConfig") -> WindowGeometry:
    return WindowGeometry(configs.WIDTH, configs.HEIGHT, maximized=configs.MAXIMIZED)


def read_geometry(path: Path) -> Optional[WindowGeometry]:
    """The geometry saved in ``path``, or None when there is none or it is unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        x, y = data.get("x"), data.get("y")
        return WindowGeometry(
            width=int(data["width"]),
            height=int(data["height"]),
            x=None if x is None else int(x),
            y=None if y is None else int(y),
            maximized=bool(data.get("maximized", False)),
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def save_geometry(path: Path, geometry: WindowGeometry) -> None:
    try:
        path.write_text(json.dumps(asdict(geometry)), encoding="utf-8")
    except OSError:
        pass  # a window that cannot remember its size is no reason to fail


def on_a_screen(geometry: WindowGeometry, screens: Sequence[Any]) -> bool:
    """
    Whether enough of the window is on one of ``screens`` to be reached, for
    example after the monitor it was on was disconnected. True when the
    screens are unknown.
    """
    if geometry.x is None or geometry.y is None or not screens:
        return True
    for screen in screens:
        visible_width = min(geometry.x + geometry.width, screen.x + screen.width) - max(
            geometry.x, screen.x
        )
        visible_height = min(
            geometry.y + geometry.height, screen.y + screen.height
        ) - max(geometry.y, screen.y)
        if visible_width >= min(_VISIBLE_WIDTH, geometry.width) and (
            visible_height >= min(_VISIBLE_HEIGHT, geometry.height)
        ):
            return True
    return False


def initial_geometry(
    configs: "DesktopConfig", saved: Optional[WindowGeometry], screens: Sequence[Any]
) -> WindowGeometry:
    """The geometry to open the window with: the saved one, when it still fits."""
    if saved is None:
        return default_geometry(configs)
    geometry = replace(
        saved,
        width=max(saved.width, configs.MIN_WIDTH),
        height=max(saved.height, configs.MIN_HEIGHT),
    )
    if not on_a_screen(geometry, screens):
        geometry = replace(geometry, x=None, y=None)
    return geometry


class GeometryTracker:
    """Follows a window's events and keeps its normal (not maximized) geometry."""

    def __init__(
        self, geometry: WindowGeometry, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._normal = replace(geometry, maximized=False)
        self._maximized = geometry.maximized
        self._minimized = False
        self._settled_after: Optional[float] = None  # None: not shown yet
        # (time, normal geometry before the change), newest last
        self._history: list[tuple[float, WindowGeometry]] = []

    def attach(self, window: Any) -> None:
        window.events.shown += self.shown
        window.events.resized += self.resized
        window.events.moved += self.moved
        window.events.maximized += self.maximized
        window.events.minimized += self.minimized
        window.events.restored += self.restored

    def resized(self, width: int, height: int) -> None:
        self._change(width=int(width), height=int(height))

    def moved(self, x: int, y: int) -> None:
        self._change(x=int(x), y=int(y))

    def shown(self) -> None:
        with self._lock:
            self._settled_after = self._clock() + _SETTLE_SECONDS

    def maximized(self) -> None:
        with self._lock:
            self._maximized = True
            self._undo_recent()

    def minimized(self) -> None:
        with self._lock:
            self._minimized = True
            self._undo_recent()

    def restored(self) -> None:
        with self._lock:
            self._maximized = False
            self._minimized = False

    def geometry(self) -> WindowGeometry:
        with self._lock:
            return replace(self._normal, maximized=self._maximized)

    def _change(self, **values: Any) -> None:
        with self._lock:
            settled = (
                self._settled_after is not None and self._clock() >= self._settled_after
            )
            if not settled or self._maximized or self._minimized:
                return
            self._history.append((self._clock(), self._normal))
            del self._history[:-20]
            self._normal = replace(self._normal, **values)

    def _undo_recent(self) -> None:
        cutoff = self._clock() - _MAXIMIZE_SECONDS
        while self._history and self._history[-1][0] >= cutoff:
            _, self._normal = self._history.pop()


def window_options(
    configs: "DesktopConfig", geometry: WindowGeometry
) -> dict[str, Any]:
    """Arguments of ``webview.create_window``, apart from the title and URL."""
    return {
        "width": geometry.width,
        "height": geometry.height,
        "x": geometry.x,
        "y": geometry.y,
        "min_size": (configs.MIN_WIDTH, configs.MIN_HEIGHT),
        "maximized": geometry.maximized,
        "fullscreen": configs.FULLSCREEN,
        "resizable": configs.RESIZABLE,
        "on_top": configs.ON_TOP,
        "confirm_close": configs.CONFIRM_CLOSE,
        "background_color": configs.BACKGROUND_COLOR,
        "text_select": configs.TEXT_SELECT,
        "zoomable": configs.ZOOMABLE,
    }


def start_options(
    configs: "DesktopConfig",
    data_folder: Path,
    *,
    dev_tools: bool,
    icon: Optional[Path],
) -> dict[str, Any]:
    """Arguments of ``webview.start``."""
    options: dict[str, Any] = {
        "debug": dev_tools,
        # pywebview's private mode forgets cookies and local storage at every
        # close, which would sign the user out each time.
        "private_mode": not configs.PERSIST_STORAGE,
        "gui": configs.GUI,
    }
    if configs.PERSIST_STORAGE:
        storage = data_folder / STORAGE_FOLDER_NAME
        storage.mkdir(parents=True, exist_ok=True)
        # The application's own folder, not pywebview's default, which every
        # pywebview program on the computer shares.
        options["storage_path"] = str(storage)
    if icon is not None:
        options["icon"] = str(icon)
    return options


def open_window(
    title: str,
    url: str,
    configs: "DesktopConfig",
    data_folder: Path,
    *,
    dev_tools: bool,
    icon: Optional[Path] = None,
) -> None:
    """Shows ``url`` in a window; returns when the window is closed."""
    import webview

    remember = configs.REMEMBER_GEOMETRY and not configs.FULLSCREEN
    geometry_file = data_folder / GEOMETRY_FILE_NAME
    saved = read_geometry(geometry_file) if remember else None
    # Asking for the screens starts pywebview's default GUI, so not when
    # another one is chosen; the saved position is then trusted.
    screens = _screens(webview) if saved is not None and not configs.GUI else []
    geometry = initial_geometry(configs, saved, screens)

    window = webview.create_window(title, url, **window_options(configs, geometry))
    tracker = GeometryTracker(geometry) if remember and window is not None else None
    if tracker is not None:
        tracker.attach(window)
    # The dev tools open from the page's context menu ("Inspect"), not by
    # themselves at every start.
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.start(**start_options(configs, data_folder, dev_tools=dev_tools, icon=icon))
    if tracker is not None:
        save_geometry(geometry_file, tracker.geometry())


def _screens(webview: Any) -> list[Any]:
    try:
        return list(webview.screens)
    except Exception:
        return []
