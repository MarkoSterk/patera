import time
import socket
import sys
import os
import signal
from typing import TYPE_CHECKING, Any, cast
import subprocess
from patera.cli import CLIController, cli_controller, command
from patera import Patera
import webview

if TYPE_CHECKING:
    from .desktop import Desktop


@cli_controller(name="desktop")
class DesktopCLI(CLIController[Patera]):
    def __init__(self, app: Patera, desktop_ext: "Desktop"):
        self._desktop_ext = desktop_ext
        super().__init__(app)

    def wait_for_server(self, host: str, port: int) -> None:
        timeout: int = self._desktop_ext.configs.STARTUP_WAIT_TIME
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.2)

        raise RuntimeError(f"Patera server did not start on time. Timeout: {timeout} s")

    def start_server_process(self) -> subprocess.Popen[Any]:
        debug: str = self._desktop_ext.app.configs.DEBUG
        env = None if debug else os.environ.copy()
        mode: str = "dev" if debug else "prod"
        if sys.platform == "win32":
            return subprocess.Popen(
                ["patera", mode],
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )

        return subprocess.Popen(
            ["patera", mode],
            env=env,
            start_new_session=True,
        )

    def stop_server_process(
        self,
        server: subprocess.Popen[Any],
        *,
        timeout: float = 10.0,
    ) -> None:
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

    def start_desktop_app(self) -> None:
        server = self.start_server_process()
        name: str = self._desktop_ext.app.configs.APP_NAME
        host: str = self._desktop_ext.app.configs.HOST
        port: int = self._desktop_ext.app.configs.PORT
        window_kwargs: dict[str, Any] = self._desktop_ext.configs.window_kwargs()
        debug: bool = self._desktop_ext.app.configs.DEBUG

        try:
            self.wait_for_server(host, port)
            window: webview.Window = cast(
                webview.Window,
                webview.create_window(
                    name,
                    **window_kwargs,
                ),
            )
            self._desktop_ext.main_window = window
            exposed_tools = self._desktop_ext.exposed_tools
            self._desktop_ext.app.logger.info(
                f"Exposed {len(exposed_tools)} tools to the frontend"
            )
            window.expose(*exposed_tools)
            webview.start(
                menu=self._desktop_ext.menu(),
                debug=debug,
                icon=self._desktop_ext.icon()
                if sys.platform.startswith("linux")
                else None,
            )
        finally:
            self.stop_server_process(server)

    @command("start")
    async def start(self) -> None:
        self.start_desktop_app()
