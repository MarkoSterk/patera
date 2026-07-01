"""
Desktop launcher for Patera applications.

The launcher runs in the main process and owns pywebview.
The HTTP server is started as a child process.
"""

from __future__ import annotations
import importlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

import webview


class DesktopSettings(BaseSettings):
    """
    Settings used by the Patera desktop launcher.

    These settings are intentionally independent of the Patera application
    instance. The launcher should not need to instantiate the app just to open
    a desktop window.
    """

    model_config = SettingsConfigDict(
        env_prefix="PATERA_DESKTOP_",
        extra="ignore",
        case_sensitive=False,
    )

    # Server/browser target -------------------------------------------------

    HOST: str = Field(
        default="localhost",
        description="Host used by the desktop launcher and child server process.",
    )

    PORT: int = Field(
        default=3000,
        description="Port used by the desktop launcher and child server process.",
    )

    URL: str | None = Field(
        default=None,
        description=(
            "Explicit URL opened in the desktop window. If omitted, the launcher "
            "builds http://<host>:<port>."
        ),
    )

    STARTUP_WAIT_TIME: float = Field(
        default=10.0,
        description="Maximum number of seconds to wait for the server to start.",
    )

    # Window ----------------------------------------------------------------

    TITLE: str = Field(
        default="Patera",
        description="Desktop window title.",
    )

    WIDTH: int = Field(
        default=1200,
        description="Initial window width.",
    )

    HEIGHT: int = Field(
        default=800,
        description="Initial window height.",
    )

    MIN_WIDTH: int | None = Field(
        default=None,
        description="Minimum window width.",
    )

    MIN_HEIGHT: int | None = Field(
        default=None,
        description="Minimum window height.",
    )

    RESIZABLE: bool = Field(
        default=True,
        description="Whether the window is resizable.",
    )

    FULLSCREEN: bool = Field(
        default=False,
        description="Whether the window starts in fullscreen mode.",
    )

    ON_TOP: bool = Field(
        default=False,
        description="Whether the window should stay on top.",
    )

    CONFIRM_CLOSE: bool = Field(
        default=False,
        description="Whether pywebview should ask for close confirmation.",
    )

    TEXT_SELECT: bool = Field(
        default=False,
        description="Whether text selection is enabled inside the webview.",
    )

    BACKGROUND_COLOR: str | None = Field(
        default=None,
        description="Window background color.",
    )

    FRAMELESS: bool | None = Field(
        default=None,
        description="Whether the window should be frameless.",
    )

    EASY_DRAG: bool | None = Field(
        default=None,
        description="Whether frameless windows can be dragged easily.",
    )

    # Runtime ---------------------------------------------------------------

    DEBUG: bool | None = Field(
        default=None,
        description=(
            "pywebview debug mode. If omitted, dev mode enables debug and prod "
            "mode disables it."
        ),
    )

    ICON: Path | None = Field(
        default=None,
        description="Path to the desktop window icon.",
    )

    MENU_PROVIDER: str | None = Field(
        default=None,
        description=(
            "Optional import string returning a pywebview menu object. "
            "Example: myapp.desktop:get_menu"
        ),
    )

    @field_validator("HOST")
    @classmethod
    def validate_host(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("host must not be empty")

        return value

    @field_validator("PORT")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value <= 0 or value > 65535:
            raise ValueError("port must be between 1 and 65535")

        return value

    @field_validator("WIDTH", "HEIGHT", "MIN_WIDTH", "MIN_HEIGHT")
    @classmethod
    def validate_positive_size(cls, value: int) -> int:
        if value is not None and value <= 0:
            raise ValueError("window size values must be greater than 0")

        return value

    @field_validator("STARTUP_WAIT_TIME")
    @classmethod
    def validate_startup_wait_time(cls, value: float) -> float:
        if value is not None and value <= 0:
            raise ValueError("startup_wait_time must be greater than 0")

        return value

    def browser_host(self) -> str:
        """
        Return a host that can be used by the embedded browser.

        Binding the server to 0.0.0.0 is valid, but opening
        http://0.0.0.0:3000 in a browser is not ideal.
        """
        if self.HOST in {"0.0.0.0", "::"}:
            return "127.0.0.1"

        return self.HOST

    def resolved_url(self) -> str:
        """
        Return the URL that should be opened in pywebview.
        """
        if self.URL:
            return self.URL

        return f"http://{self.browser_host()}:{self.PORT}"

    def resolved_debug(self, mode: str) -> bool:
        """
        Return pywebview debug mode.

        If PATERA_DESKTOP_DEBUG is not set, dev mode enables debug and prod mode
        disables it.
        """
        if self.DEBUG is not None:
            return self.DEBUG

        return mode == "dev"

    def resolved_icon(self, cwd: Path) -> str | None:
        """
        Return the icon path as a string, resolving relative paths against cwd.
        """
        if self.ICON is None:
            return None

        if self.ICON.is_absolute():
            return str(self.ICON.resolve())

        return str((cwd / self.ICON).resolve())

    def window_kwargs(self) -> dict[str, Any]:
        """
        Build keyword arguments for webview.create_window().
        """
        kwargs: dict[str, Any] = {
            "url": self.resolved_url(),
            "width": self.WIDTH,
            "height": self.HEIGHT,
            "resizable": self.RESIZABLE,
            "fullscreen": self.FULLSCREEN,
            "on_top": self.ON_TOP,
            "confirm_close": self.CONFIRM_CLOSE,
            "text_select": self.TEXT_SELECT,
        }

        if self.MIN_WIDTH is not None or self.MIN_HEIGHT is not None:
            kwargs["min_size"] = (
                self.MIN_WIDTH or self.WIDTH,
                self.MIN_HEIGHT or self.HEIGHT,
            )

        if self.BACKGROUND_COLOR is not None:
            kwargs["background_color"] = self.BACKGROUND_COLOR

        if self.FRAMELESS is not None:
            kwargs["frameless"] = self.FRAMELESS

        if self.EASY_DRAG is not None:
            kwargs["easy_drag"] = self.EASY_DRAG

        return kwargs


def import_object(import_path: str) -> Any:
    """
    Import an object from an import string.

    Example:

        myapp.desktop:get_tools
        myapp.desktop:get_menu
    """
    if ":" not in import_path:
        raise ValueError(
            f"Invalid import path '{import_path}'. "
            "Expected format: module.submodule:object_name"
        )

    module_name, object_name = import_path.split(":", 1)

    module = importlib.import_module(module_name)
    return getattr(module, object_name)


class DesktopLauncher:
    """
    Launches a Patera app as a desktop application.

    This class does not instantiate the Patera app. It only receives the resolved
    Patera app import path and starts the normal Patera HTTP server as a child
    process.
    """

    def __init__(
        self,
        *,
        app_path: str,
        cwd: str | Path,
        mode: str = "dev",
        env_file: str | None = None,
        settings: DesktopSettings | None = None,
    ) -> None:
        if mode not in {"dev", "prod"}:
            raise ValueError("Desktop mode must be either 'dev' or 'prod'")

        self.app_path = app_path
        self.cwd = Path(cwd).resolve()
        self.mode = mode
        self.env_file = env_file
        self.settings = settings or DesktopSettings()

        self.server: subprocess.Popen[Any] | None = None
        self.main_window: webview.Window | None = None

    def server_command(self) -> list[str]:
        """
        Build the command used to start the Patera server.
        """
        command = [
            "patera",
            self.mode,
            "--app",
            self.app_path,
        ]

        if self.env_file is not None:
            command.extend(["--env-file", self.env_file])

        return command

    def start_server_process(self) -> subprocess.Popen[Any]:
        """
        Start the Patera HTTP server as a child process.
        """
        command = self.server_command()

        if sys.platform == "win32":
            return subprocess.Popen(
                command,
                cwd=str(self.cwd),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )

        return subprocess.Popen(
            command,
            cwd=str(self.cwd),
            start_new_session=True,
        )

    def wait_for_server(self) -> None:
        """
        Wait until the child HTTP server accepts TCP connections.
        """
        deadline = time.time() + self.settings.STARTUP_WAIT_TIME

        while time.time() < deadline:
            if self.server is not None and self.server.poll() is not None:
                raise RuntimeError(
                    "Patera server process exited before the desktop window started"
                )

            try:
                with socket.create_connection(
                    (
                        self.settings.browser_host(),
                        self.settings.PORT,
                    ),
                    timeout=0.5,
                ):
                    return

            except OSError:
                time.sleep(0.2)

        raise RuntimeError(
            "Patera server did not start on time. "
            f"Timeout: {self.settings.STARTUP_WAIT_TIME} s"
        )

    def stop_server_process(
        self,
        server: subprocess.Popen[Any],
        *,
        timeout: float = 10.0,
    ) -> None:
        """
        Stop the server process gracefully, then forcefully if needed.
        """
        if server.poll() is not None:
            return

        try:
            if sys.platform == "win32":
                server.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(server.pid, signal.SIGINT)

            server.wait(timeout=timeout)
            return

        except subprocess.TimeoutExpired:
            pass

        except ProcessLookupError:
            return

        if server.poll() is not None:
            return

        try:
            if sys.platform == "win32":
                server.terminate()
            else:
                os.killpg(server.pid, signal.SIGTERM)

            server.wait(timeout=5)
            return

        except subprocess.TimeoutExpired:
            pass

        except ProcessLookupError:
            return

        if server.poll() is not None:
            return

        if sys.platform == "win32":
            server.kill()
        else:
            os.killpg(server.pid, signal.SIGKILL)

        server.wait(timeout=5)

    def load_menu(self) -> Any:
        """
        Load an optional pywebview menu.

        PATERA_DESKTOP_MENU_PROVIDER should point to a callable returning a menu
        object compatible with pywebview.start(menu=...).

        Example:

            PATERA_DESKTOP_MENU_PROVIDER=myapp.desktop:get_menu
        """
        if self.settings.MENU_PROVIDER is None:
            return None

        provider = import_object(self.settings.MENU_PROVIDER)

        if not callable(provider):
            raise TypeError("PATERA_DESKTOP_MENU_PROVIDER must point to a callable")

        return provider()

    def create_window(self) -> webview.Window:
        """
        Create and configure the pywebview window.
        """
        window = cast(
            webview.Window,
            webview.create_window(
                self.settings.TITLE,
                **self.settings.window_kwargs(),
            ),
        )
        self.main_window = window
        return window

    def start_webview(self) -> None:
        """
        Start pywebview.

        This method must run in the main thread.
        """
        self.create_window()

        icon = self.settings.resolved_icon(self.cwd)

        webview.start(
            menu=self.load_menu(),
            debug=self.settings.resolved_debug(self.mode),
            icon=icon if sys.platform.startswith("linux") else None,
        )

    def start(self) -> None:
        """
        Start the server subprocess and open the desktop window.
        """
        self.server = self.start_server_process()

        try:
            self.wait_for_server()
            self.start_webview()

        finally:
            if self.server is not None:
                self.stop_server_process(self.server)
