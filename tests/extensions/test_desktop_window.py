"""
The desktop window: options from the DESKTOP settings, and the size and
position remembered between starts. pywebview is replaced by a stand-in,
so no GUI is needed.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("patera.desktop")

from pydantic import ValidationError  # noqa: E402

from patera.desktop import Desktop, DesktopConfig  # noqa: E402
from patera.desktop import desktop as desktop_module  # noqa: E402
from patera.desktop import window as window_module  # noqa: E402
from patera.desktop.window import (  # noqa: E402
    GEOMETRY_FILE_NAME,
    GeometryTracker,
    WindowGeometry,
    initial_geometry,
    read_geometry,
    save_geometry,
)

pytestmark = pytest.mark.integration


class _Screen:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height


class _Event:
    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "_Event":
        self.handlers.append(handler)
        return self

    def fire(self, *args: Any) -> None:
        for handler in self.handlers:
            handler(*args)


class _FakeWebview(types.ModuleType):
    """Records create_window() and start(); start() plays the given events."""

    def __init__(self, screens: list[_Screen], play: list[tuple[str, tuple]]) -> None:
        super().__init__("webview")
        self.screens = screens
        self.play = play
        self.settings = {"OPEN_DEVTOOLS_IN_DEBUG": True}
        self.created: dict[str, Any] = {}
        self.started: dict[str, Any] = {}
        self.window = types.SimpleNamespace(
            events=types.SimpleNamespace(
                **{
                    name: _Event()
                    for name in (
                        "shown",
                        "resized",
                        "moved",
                        "maximized",
                        "minimized",
                        "restored",
                    )
                }
            )
        )

    def create_window(self, title: str, url: str, **options: Any) -> Any:
        self.created = {"title": title, "url": url, **options}
        return self.window

    def start(self, **options: Any) -> None:
        self.started = options
        for name, args in self.play:
            getattr(self.window.events, name).fire(*args)


@pytest.fixture(autouse=True)
def no_settling(monkeypatch):
    # Changes count right after "shown", instead of a second later.
    monkeypatch.setattr(window_module, "_SETTLE_SECONDS", 0.0)


@pytest.fixture
def webview(monkeypatch):
    def install(screens=None, play=()):
        fake = _FakeWebview(
            [_Screen(0, 0, 1920, 1080)] if screens is None else screens, list(play)
        )
        monkeypatch.setitem(sys.modules, "webview", fake)
        return fake

    return install


# ---- settings ---------------------------------------------------------------------


def test_window_settings_have_sensible_defaults():
    configs = DesktopConfig()
    assert (configs.WIDTH, configs.HEIGHT) == (1024, 720)
    assert (configs.MIN_WIDTH, configs.MIN_HEIGHT) == (480, 360)
    assert configs.REMEMBER_GEOMETRY and configs.PERSIST_STORAGE and configs.TEXT_SELECT
    assert configs.TITLE is None and configs.DEV_TOOLS is None


@pytest.mark.parametrize(
    "values",
    [
        {"WIDTH": 400},  # below MIN_WIDTH
        {"MIN_HEIGHT": 800},  # above HEIGHT
        {"BACKGROUND_COLOR": "white"},
        {"WIDTH": 50, "MIN_WIDTH": 50},
    ],
)
def test_impossible_window_settings_are_refused(values):
    with pytest.raises(ValidationError):
        DesktopConfig(**values)


# ---- geometry ---------------------------------------------------------------------


def test_the_first_start_uses_the_settings():
    configs = DesktopConfig(WIDTH=900, HEIGHT=600, MAXIMIZED=True)
    assert initial_geometry(configs, None, []) == WindowGeometry(
        900, 600, maximized=True
    )


def test_a_saved_geometry_is_used_when_it_still_fits():
    configs = DesktopConfig()
    screens = [_Screen(0, 0, 1920, 1080), _Screen(1920, 0, 1280, 1024)]
    saved = WindowGeometry(1200, 800, 2000, 100, maximized=True)
    assert initial_geometry(configs, saved, screens) == saved
    # Smaller than allowed now (MIN_* raised since): enlarged.
    assert initial_geometry(configs, WindowGeometry(300, 200, 10, 10), screens) == (
        WindowGeometry(480, 360, 10, 10)
    )


def test_a_window_on_a_missing_screen_is_centered():
    configs = DesktopConfig()
    # It was on a second monitor, which is gone.
    saved = WindowGeometry(1200, 800, 2000, 100)
    assert initial_geometry(configs, saved, [_Screen(0, 0, 1920, 1080)]) == (
        WindowGeometry(1200, 800)
    )
    # Only its edge would be visible: not reachable either.
    edge = WindowGeometry(1200, 800, 1900, 1060)
    assert initial_geometry(configs, edge, [_Screen(0, 0, 1920, 1080)]).x is None
    # Unknown screens: the saved position is trusted.
    assert initial_geometry(configs, saved, []) == saved


def test_geometry_files(tmp_path):
    path = tmp_path / GEOMETRY_FILE_NAME
    assert read_geometry(path) is None
    save_geometry(path, WindowGeometry(800, 600, -5, 20, maximized=True))
    assert read_geometry(path) == WindowGeometry(800, 600, -5, 20, maximized=True)
    path.write_text("{not json", encoding="utf-8")
    assert read_geometry(path) is None
    path.write_text(json.dumps({"width": "wide"}), encoding="utf-8")
    assert read_geometry(path) is None


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_the_tracker_keeps_the_normal_geometry():
    clock = _Clock()
    tracker = GeometryTracker(WindowGeometry(1024, 720), clock=clock)
    tracker.shown()
    tracker.resized(900, 700)
    tracker.moved(40, 30)
    assert tracker.geometry() == WindowGeometry(900, 700, 40, 30)

    # Maximizing: the toolkit reports the new size just before the maximize.
    clock.now += 5
    tracker.moved(0, 0)
    tracker.resized(1920, 1040)
    clock.now += 0.1
    tracker.maximized()
    assert tracker.geometry() == WindowGeometry(900, 700, 40, 30, maximized=True)
    # ...or after it: ignored while maximized.
    tracker.resized(1920, 1040)
    assert tracker.geometry() == WindowGeometry(900, 700, 40, 30, maximized=True)

    tracker.restored()
    clock.now += 5
    tracker.resized(1000, 650)
    assert tracker.geometry() == WindowGeometry(1000, 650, 40, 30)

    # Minimizing on Windows moves the window far away first.
    clock.now += 5
    tracker.moved(-32000, -32000)
    tracker.minimized()
    tracker.restored()
    assert tracker.geometry() == WindowGeometry(1000, 650, 40, 30)


def test_placing_the_window_is_not_a_change(monkeypatch):
    monkeypatch.setattr(window_module, "_SETTLE_SECONDS", 1.0)
    clock = _Clock()
    tracker = GeometryTracker(WindowGeometry(900, 640, 120, 80), clock=clock)
    # Qt reports the position it was given a frame's width off.
    tracker.moved(118, 78)
    tracker.shown()
    tracker.moved(118, 78)
    clock.now += 0.5
    tracker.resized(902, 642)
    assert tracker.geometry() == WindowGeometry(900, 640, 120, 80)
    clock.now += 1.0
    tracker.moved(300, 200)  # the user's move
    assert tracker.geometry() == WindowGeometry(900, 640, 300, 200)


# ---- the window -------------------------------------------------------------------


def _configs(**values: Any) -> DesktopConfig:
    return DesktopConfig(**values)


def test_the_window_is_created_from_the_settings(webview, tmp_path):
    fake = webview()
    configs = _configs(
        WIDTH=900,
        HEIGHT=650,
        ON_TOP=True,
        BACKGROUND_COLOR="#1E2125",
        ZOOMABLE=True,
        GUI="qt",
    )
    window_module.open_window(
        "Notes",
        "http://127.0.0.1:5000/",
        configs,
        tmp_path,
        dev_tools=True,
        icon=tmp_path / "icon.png",
    )
    assert fake.created == {
        "title": "Notes",
        "url": "http://127.0.0.1:5000/",
        "width": 900,
        "height": 650,
        "x": None,
        "y": None,
        "min_size": (480, 360),
        "maximized": False,
        "fullscreen": False,
        "resizable": True,
        "on_top": True,
        "confirm_close": False,
        "background_color": "#1E2125",
        "text_select": True,
        "zoomable": True,
    }
    assert fake.started == {
        "debug": True,
        "private_mode": False,
        "gui": "qt",
        "storage_path": str(tmp_path / "webview"),
        "icon": str(tmp_path / "icon.png"),
    }
    assert (tmp_path / "webview").is_dir()
    # The inspector is available, but does not open by itself.
    assert fake.settings["OPEN_DEVTOOLS_IN_DEBUG"] is False


def test_private_storage(webview, tmp_path):
    fake = webview()
    window_module.open_window(
        "Notes", "http://x/", _configs(PERSIST_STORAGE=False), tmp_path, dev_tools=False
    )
    assert fake.started == {"debug": False, "private_mode": True, "gui": None}
    assert not (tmp_path / "webview").exists()


def test_the_window_reopens_as_it_was_closed(webview, tmp_path):
    fake = webview(play=[("shown", ()), ("resized", (1100, 760)), ("moved", (60, 45))])
    window_module.open_window(
        "Notes", "http://x/", _configs(), tmp_path, dev_tools=False
    )
    assert fake.created["x"] is None  # first start: centered
    assert read_geometry(tmp_path / GEOMETRY_FILE_NAME) == WindowGeometry(
        1100, 760, 60, 45
    )

    fake = webview(play=[("shown", ()), ("maximized", ())])
    window_module.open_window(
        "Notes", "http://x/", _configs(), tmp_path, dev_tools=False
    )
    assert (fake.created["width"], fake.created["height"]) == (1100, 760)
    assert (fake.created["x"], fake.created["y"]) == (60, 45)
    assert read_geometry(tmp_path / GEOMETRY_FILE_NAME) == WindowGeometry(
        1100, 760, 60, 45, maximized=True
    )

    fake = webview(screens=[_Screen(0, 0, 1366, 768)])
    window_module.open_window(
        "Notes", "http://x/", _configs(), tmp_path, dev_tools=False
    )
    assert fake.created["maximized"] is True
    assert (fake.created["x"], fake.created["y"]) == (60, 45)


@pytest.mark.parametrize("values", [{"REMEMBER_GEOMETRY": False}, {"FULLSCREEN": True}])
def test_geometry_that_is_not_remembered(webview, tmp_path, values):
    save_geometry(tmp_path / GEOMETRY_FILE_NAME, WindowGeometry(1500, 900, 5, 5))
    fake = webview(play=[("shown", ()), ("resized", (700, 500))])
    window_module.open_window(
        "Notes", "http://x/", _configs(**values), tmp_path, dev_tools=False
    )
    assert (fake.created["width"], fake.created["x"]) == (1024, None)
    # The file is left as it was.
    assert read_geometry(tmp_path / GEOMETRY_FILE_NAME) == WindowGeometry(
        1500, 900, 5, 5
    )


# ---- the application's window ------------------------------------------------------


def test_show_window_uses_the_applications_settings(make_app, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "data"))
    monkeypatch.setattr(desktop_module.Path, "home", lambda: tmp_path / "home")
    app = make_app(
        extensions=[Desktop],
        cli_mode=True,
        APP_NAME="Ledger",
        DESKTOP={"ICON": "static/ledger.png"},
    )
    opened: dict[str, Any] = {}

    def fake_open(title, url, configs, data_folder, *, dev_tools, icon=None):
        opened.update(title=title, url=url, data_folder=data_folder, icon=icon)

    monkeypatch.setattr(desktop_module, "open_window", fake_open)
    desktop_module.show_window(app, "http://127.0.0.1:1/", dev_tools=False)
    assert opened["title"] == "Ledger"
    assert opened["data_folder"] == desktop_module.user_data_dir("Ledger")
    assert opened["icon"] == Path(app.root_path) / "static" / "ledger.png"

    app = make_app(extensions=[Desktop], cli_mode=True, DESKTOP={"TITLE": "My ledger"})
    desktop_module.show_window(app, "http://127.0.0.1:1/", dev_tools=False)
    assert opened["title"] == "My ledger" and opened["icon"] is None


def test_a_program_keeps_its_port(monkeypatch, tmp_path):
    import socket

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "data"))
    monkeypatch.setattr(desktop_module.Path, "home", lambda: tmp_path / "home")
    first = desktop_module.installation_port("Ledger")
    port_file = desktop_module.user_data_dir("Ledger") / desktop_module.PORT_FILE_NAME
    assert port_file.read_text() == str(first)
    # The next start uses it again: the page keeps its origin and storage.
    assert desktop_module.installation_port("Ledger") == first

    # Taken by something else: another port, kept from then on.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind((desktop_module.HOST, first))
        busy.listen()
        second = desktop_module.installation_port("Ledger")
    assert second != first and port_file.read_text() == str(second)

    port_file.write_text("not a port")
    assert 1024 <= desktop_module.installation_port("Ledger") <= 65535


def test_desktop_run_enables_the_inspector_in_dev_mode(make_app):
    desktop = make_app(extensions=[Desktop], cli_mode=True).get_extension(Desktop)
    assert desktop.dev_tools("dev") is True
    assert desktop.dev_tools("prod") is False
    desktop = make_app(
        extensions=[Desktop], cli_mode=True, DESKTOP={"DEV_TOOLS": False}
    ).get_extension(Desktop)
    assert desktop.dev_tools("dev") is False


def test_the_spec_file_takes_the_icon(make_app, tmp_path):
    from patera.desktop.packaging import spec_text

    app = make_app(extensions=[Desktop], cli_mode=True, DESKTOP={"ICON": "app.ico"})
    root = Path(app.root_path)
    text = spec_text(app, root.parent / "desktop.spec")
    assert f'ICON = "{root.name}/app.ico"' in text
    plain = make_app(extensions=[Desktop], cli_mode=True)
    assert "ICON = None" in spec_text(plain, tmp_path / "desktop.spec")
