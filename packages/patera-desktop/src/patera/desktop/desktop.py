"""
Desktop applications with Patera and pywebview.

Register the extension:

    class App(Patera):
        app_extensions = [Desktop]

During development, ``patera cli desktop:run`` (or ``desktop:run prod``)
starts the application in a separate process, as ``patera dev`` or
``patera prod`` would, and shows it in a window; closing the window stops
the application.

For a packaged application, ``run_in_window(App)`` runs the server inside
the same process, on a background thread, and the window on the main
thread. ``patera cli desktop:package`` builds such an application with
PyInstaller, and ``patera cli desktop:spec`` writes the spec file it builds
with, for editing.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Optional, Self, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from patera.base_extension import BaseExtension
from patera.cli import CLIController, cli_controller, command

from .packaging import DEFAULT_SPEC_FILE
from .window import open_window

if TYPE_CHECKING:
    from patera import Patera

AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")

#: The application only listens on this computer.
HOST = "127.0.0.1"
#: Seconds to wait for the application to answer.
STARTUP_TIMEOUT = 60.0
#: Seconds the application gets to shut down before it is killed.
SHUTDOWN_TIMEOUT = 10.0
#: Output folder of ``desktop:package``, relative to the project folder.
DEFAULT_PACKAGE_FOLDER = "dist/desktop"
#: File in the user's data folder with the settings of one installation.
SETTINGS_FILE_NAME = "settings.env"
#: File in the user's data folder with the port the program listened on.
PORT_FILE_NAME = "port"


class DesktopConfig(BaseModel):
    """Settings of the Desktop extension (``DESKTOP``)."""

    INDEX_PAGE: str = Field(
        "/",
        description=(
            "Page the window opens: a path of the application, relative to "
            "URL_PREFIX ('/', '/dashboard'), or an absolute URL."
        ),
    )
    TITLE: Optional[str] = Field(
        None, description="Window title. Not set: the application's APP_NAME."
    )
    WIDTH: int = Field(1024, ge=100, description="Window width (logical pixels).")
    HEIGHT: int = Field(720, ge=100, description="Window height (logical pixels).")
    MIN_WIDTH: int = Field(
        480, ge=100, description="The narrowest the user can make the window."
    )
    MIN_HEIGHT: int = Field(
        360, ge=100, description="The lowest the user can make the window."
    )
    REMEMBER_GEOMETRY: bool = Field(
        True,
        description=(
            "Reopen the window with the size, position and maximized state it "
            "had when it was closed (kept in the user's data folder). WIDTH, "
            "HEIGHT and MAXIMIZED then apply only to the first start."
        ),
    )
    MAXIMIZED: bool = Field(False, description="Open the window maximized.")
    FULLSCREEN: bool = Field(False, description="Open the window in full screen.")
    RESIZABLE: bool = Field(True, description="The user can resize the window.")
    ON_TOP: bool = Field(False, description="Keep the window above other windows.")
    CONFIRM_CLOSE: bool = Field(
        False, description="Ask the user to confirm before the window closes."
    )
    BACKGROUND_COLOR: str = Field(
        "#FFFFFF",
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description=(
            "Color shown before the page has loaded; set it to the page's "
            "background to avoid a flash, for example in a dark design."
        ),
    )
    TEXT_SELECT: bool = Field(
        True, description="The user can select (and copy) the page's text."
    )
    ZOOMABLE: bool = Field(
        False, description="The user can zoom the page (Ctrl and +/-)."
    )
    PERSIST_STORAGE: bool = Field(
        True,
        description=(
            "Keep cookies and local storage between starts, in the user's data "
            "folder. Off: they are forgotten when the window closes, so for "
            "example every start signs the user out."
        ),
    )
    ICON: Optional[str] = Field(
        None,
        description=(
            "Icon file, relative to the application's root folder (.ico on "
            "Windows, .icns on macOS, .png on Linux). Linux uses it for the "
            "window; on Windows and macOS the window shows the executable's "
            "icon, which desktop:spec takes from this setting."
        ),
    )
    DEV_TOOLS: Optional[bool] = Field(
        None,
        description=(
            "The web inspector, from the page's context menu. Not set: on for "
            "desktop:run in dev mode and when DEBUG is on, off otherwise."
        ),
    )
    GUI: Optional[str] = Field(
        None,
        description=(
            "pywebview's GUI toolkit, for example 'qt' or 'gtk' on Linux. Not "
            "set: pywebview chooses."
        ),
    )

    @model_validator(mode="after")
    def _size_within_minimum(self) -> Self:
        if self.WIDTH < self.MIN_WIDTH or self.HEIGHT < self.MIN_HEIGHT:
            raise ValueError(
                "WIDTH and HEIGHT must be at least MIN_WIDTH and MIN_HEIGHT."
            )
        return self


class Desktop(BaseExtension[AppT, DesktopConfig], Generic[AppT]):
    """Adds the ``desktop:run`` and ``desktop:package`` commands."""

    def init(self) -> None:
        self.app.register_cli_controller(DesktopCLIController(self.app, self))

    def index_url(self, port: int) -> str:
        """The URL the window opens."""
        return index_url(self.app, port)

    def server_command(self, mode: str) -> list[str]:
        """``patera dev`` or ``patera prod`` for this application."""
        app_class = type(self.app)
        return [
            sys.executable,
            "-m",
            "patera.cli",
            mode,
            "--app",
            f"{app_class.__module__}:{app_class.__qualname__}",
        ]

    def start_server(self, mode: str, port: int) -> subprocess.Popen[bytes]:
        """
        Starts the application in its own process group, so stopping it also
        stops the processes it starts (the reloader's worker, for example).
        """
        environment = {**os.environ, "PATERA_HOST": HOST, "PATERA_PORT": str(port)}
        if sys.platform == "win32":
            return subprocess.Popen(
                self.server_command(mode),
                env=environment,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        return subprocess.Popen(
            self.server_command(mode), env=environment, start_new_session=True
        )

    def wait_until_ready(self, server: subprocess.Popen[bytes], port: int) -> None:
        """Waits until the application accepts connections."""
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(
                    f"The application stopped while starting (exit code {server.returncode})."
                )
            try:
                with socket.create_connection((HOST, port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError(
            f"The application did not answer on {HOST}:{port} within "
            f"{STARTUP_TIMEOUT:g} seconds."
        )

    def show_window(self, url: str, dev_tools: bool = False) -> None:
        """Shows ``url`` in a window; returns when the window is closed."""
        show_window(self.app, url, dev_tools=dev_tools)

    def stop_server(self, server: subprocess.Popen[bytes]) -> None:
        """Stops the application as Ctrl+C would, and kills it if it hangs."""
        if server.poll() is not None:
            return
        if sys.platform == "win32":
            server.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(server.pid, signal.SIGINT)
        try:
            server.wait(timeout=SHUTDOWN_TIMEOUT)
            return
        except subprocess.TimeoutExpired:
            pass
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(server.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(server.pid, signal.SIGKILL)
        server.wait()

    def run(self, mode: str = "dev") -> None:
        """Runs the application and shows it until the window is closed."""
        if mode not in ("dev", "prod"):
            raise ValueError(f"Mode must be 'dev' or 'prod', not {mode!r}.")
        port = int(self.app.configs.PORT)
        server = self.start_server(mode, port)
        try:
            self.wait_until_ready(server, port)
            self.show_window(self.index_url(port), dev_tools=self.dev_tools(mode))
        finally:
            self.stop_server(server)

    def dev_tools(self, mode: str) -> bool:
        """Whether ``desktop:run`` in ``mode`` enables the web inspector."""
        setting = self.configs.DEV_TOOLS
        return mode == "dev" if setting is None else setting

    def package(
        self, output: str = DEFAULT_PACKAGE_FOLDER, spec: str = DEFAULT_SPEC_FILE
    ) -> Path:
        """
        Packages the application with PyInstaller into ``output``, with the
        spec file ``spec`` (both relative to the current folder), and returns
        ``output``. Without the default spec file, a generated one is used.
        """
        from .packaging import package

        return package(self.app, Path(output), Path(spec))

    def write_spec(self, path: str = DEFAULT_SPEC_FILE) -> Path:
        """Writes a PyInstaller spec file with the default settings, to edit."""
        from .packaging import write_spec

        return write_spec(self.app, Path(path))


@cli_controller(name="desktop")
class DesktopCLIController(CLIController[Any]):
    def __init__(self, app: Any, desktop: Desktop[Any]) -> None:
        super().__init__(app)
        self._desktop = desktop

    @command("run", help="Run the application in a desktop window (mode: dev or prod)")
    async def run(self, mode: str = "dev") -> None:
        # Directly, not in a worker thread: GUI toolkits need the main thread.
        self._desktop.run(mode)

    @command(
        "package",
        help=(
            "Package the application with PyInstaller "
            f"(default output: {DEFAULT_PACKAGE_FOLDER}; builds with {DEFAULT_SPEC_FILE} when it exists)"
        ),
    )
    async def package(
        self, output: str = DEFAULT_PACKAGE_FOLDER, spec: str = DEFAULT_SPEC_FILE
    ) -> None:
        folder = self._desktop.package(output, spec)
        print(f"Packaged application in {folder}")

    @command(
        "spec",
        help=f"Write a PyInstaller spec file to edit (default: {DEFAULT_SPEC_FILE})",
    )
    async def spec(self, path: str = DEFAULT_SPEC_FILE) -> None:
        spec_file = self._desktop.write_spec(path)
        print(
            f"Wrote {spec_file}. Edit it for what the program needs (hidden imports, "
            "data files, an icon); desktop:package builds with it."
        )


def index_url(app: Any, port: int) -> str:
    """The URL a window opens: DESKTOP.INDEX_PAGE of the application."""
    page = _desktop_configs(app).INDEX_PAGE
    if urlparse(page).scheme:
        return page
    return f"http://{HOST}:{port}{app.url_prefix}/{page.lstrip('/')}"


def _desktop_configs(app: Any) -> DesktopConfig:
    for extension in app.extensions.values():
        if isinstance(extension, Desktop):
            return extension.configs
    return DesktopConfig.model_validate({})


def show_window(app: Any, url: str, *, dev_tools: bool) -> None:
    """
    Shows ``url`` in a pywebview window set up by the application's DESKTOP
    settings; returns when the window is closed.
    """
    configs = _desktop_configs(app)
    open_window(
        configs.TITLE or app.app_name,
        url,
        configs,
        user_data_dir(app.app_name),
        dev_tools=dev_tools,
        icon=icon_path(app),
    )


def icon_path(app: Any) -> Optional[Path]:
    """DESKTOP.ICON as a path (relative ones from the application's root folder)."""
    icon = _desktop_configs(app).ICON
    if not icon:
        return None
    path = Path(icon)
    return path if path.is_absolute() else Path(app.root_path) / path


def free_port() -> int:
    """A port on HOST that nothing listens on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def port_is_free(port: int) -> bool:
    """Whether the server can listen on ``port`` now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sys.platform != "win32":
            # As uvicorn does: a port whose last connections are still in
            # TIME_WAIT, as after the previous start, can be used again. (On
            # Windows the option would allow taking a port in use.)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
        return True


def installation_port(app_name: str) -> int:
    """
    The port a packaged application listens on: the one it used last time,
    when it is still free, otherwise a free one, kept for the next start.

    The page's origin, http://127.0.0.1:<port>, then stays the same, and with
    it the page's local storage, which browsers keep per origin (port
    included). Cookies do not depend on the port.
    """
    path = user_data_dir(app_name) / PORT_FILE_NAME
    try:
        port = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        port = 0
    if 1024 <= port <= 65535 and port_is_free(port):
        return port
    port = free_port()
    try:
        path.write_text(str(port), encoding="utf-8")
    except OSError:
        pass
    return port


_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def user_data_dir(app_name: str) -> Path:
    """
    The folder where an installed application keeps its data (logs, a
    SQLite database, ...), created if needed:

    - Windows: %APPDATA%\\<app name>
    - macOS and iOS: ~/Library/Application Support/<app name> (on iOS, in the
      app's sandbox)
    - Android: $HOME/<app name>, the app's internal storage
    - Linux: $XDG_DATA_HOME/<app name>, by default ~/.local/share/<app name>

    A packaged application's own folder may not be writable (Program Files)
    and is replaced by every update, so data belongs here.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform in ("darwin", "ios"):
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "android":
        # Embedded Python (Chaquopy, which Briefcase uses) sets HOME to the
        # app's private internal storage; files there stay until uninstall.
        base = Path.home()
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    name = _UNSAFE_NAME.sub("_", app_name).strip(" .") or "Patera app"
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def settings_file(app_name: str) -> Path:
    """
    The settings file of an installed application:
    ``user_data_dir(app_name) / "settings.env"``. ``run_in_window`` loads it
    before the application starts, like ``.env`` during development, so it
    holds what differs per user or installation. The file uses the same
    names as environment variables (``PATERA_...``); real environment
    variables win over it. The application may create or edit it, for
    example from a settings page; changes apply at the next start.
    """
    return user_data_dir(app_name) / SETTINGS_FILE_NAME


def _ensure_streams() -> None:
    """
    A windowed (console-less) executable has no standard output or error;
    logging to them would fail, so they are replaced by the null device.
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def run_in_window(app_class: "type[Patera[Any]]") -> None:
    """
    Runs the application in this process and shows it in a window until the
    window is closed: the entry point of a packaged desktop application.

    Before the application is created, the settings file of this
    installation is loaded when it exists (see settings_file()).

    The server (uvicorn) runs on a background thread, on 127.0.0.1 and the
    port of the last start when it is free (see installation_port()); the
    window needs the main thread. The application runs in
    production mode unless PATERA_DEBUG says otherwise. In a packaged
    (frozen) application, the log files go to user_data_dir() unless
    PATERA_LOG_FILES__PATH names another file.
    """
    import uvicorn
    from dotenv import load_dotenv

    _ensure_streams()
    app_name = app_class._app_configs["configs"]().APP_NAME  # type: ignore[attr-defined]
    installation_settings = settings_file(app_name)
    if installation_settings.is_file():
        # Real environment variables win, as they do over .env.
        load_dotenv(installation_settings, override=False)
    os.environ.setdefault("PATERA_DEBUG", "0")
    if getattr(sys, "frozen", False):
        os.environ.setdefault(
            "PATERA_LOG_FILES__PATH",
            str(user_data_dir(app_name) / "logs" / "patera.jsonl"),
        )

    port = installation_port(app_name)
    # The settings then report the address the application really uses.
    os.environ["PATERA_HOST"] = HOST
    os.environ["PATERA_PORT"] = str(port)
    application = app_class()
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host=HOST,
            port=port,
            lifespan="on",
            log_config=None,
            access_log=False,
        )
    )
    thread = threading.Thread(
        target=server.run, name="patera-desktop-server", daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("The application stopped while starting.")
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"The application did not start within {STARTUP_TIMEOUT:g} seconds."
                )
            time.sleep(0.05)
        setting = _desktop_configs(application).DEV_TOOLS
        dev_tools = bool(application.configs.DEBUG) if setting is None else setting
        show_window(application, index_url(application, port), dev_tools=dev_tools)
    finally:
        server.should_exit = True
        thread.join(timeout=SHUTDOWN_TIMEOUT)
