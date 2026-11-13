"""
The ASGI lifespan protocol: startup and shutdown methods, background
task draining and the logger sinks that live for one lifespan.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

import inspect
from typing import (
    Callable,
)


from ..utilities import (
    run_sync_or_async,
    wait_for_background_tasks,
)

from ._base import AppPart


class Lifespan(AppPart):
    """
    The ASGI lifespan protocol: startup and shutdown methods, background
    task draining and the logger sinks that live for one lifespan.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    def marked_methods(self, marker: str) -> list[Callable]:
        """
        Returns bound methods carrying the given decorator marker, sorted by
        name. Properties are skipped so that scanning has no side effects.
        """
        app = self._app
        methods = []

        for name in dir(type(app)):
            if isinstance(inspect.getattr_static(app, name, None), property):
                continue

            method = getattr(app, name, None)

            if callable(method) and getattr(method, marker, False):
                methods.append((name, method))

        methods.sort(key=lambda x: x[0])
        return [m for _, m in methods]

    def get_startup_methods(self) -> None:
        app = self._app
        app._on_startup_methods = app._marked_methods("_on_startup_method")

    def get_shutdown_methods(self) -> None:
        app = self._app
        app._on_shutdown_methods = app._marked_methods("_on_shutdown_method")

    async def lifespan_app(self, _, receive, send):
        """
        Handles the ASGI lifespan protocol. Startup actions run on
        ``lifespan.startup`` and shutdown actions on ``lifespan.shutdown``.
        A failing action is logged and reported to the server with
        ``lifespan.startup.failed`` or ``lifespan.shutdown.failed``.
        """
        app = self._app
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                app._attach_logger_sinks()
                try:
                    for method in app._on_startup_methods:
                        await run_sync_or_async(method)
                except Exception as exc:
                    app.logger.exception(exc)
                    await send(
                        {"type": "lifespan.startup.failed", "message": repr(exc)}
                    )
                    return

                await send({"type": "lifespan.startup.complete"})

            elif message["type"] == "lifespan.shutdown":
                try:
                    await app._finish_background_tasks()
                    for method in app._on_shutdown_methods:
                        await run_sync_or_async(method)
                except Exception as exc:
                    app.logger.exception(exc)
                    app._remove_logger_sinks()
                    await send(
                        {"type": "lifespan.shutdown.failed", "message": repr(exc)}
                    )
                    return

                app._remove_logger_sinks()

                await send({"type": "lifespan.shutdown.complete"})
                return

    async def finish_background_tasks(self) -> None:
        """
        Lets tasks from run_in_background() (emails, task manager jobs, ...)
        finish before shutdown methods close the resources they use.
        """
        app = self._app
        timeout = app.configs.BACKGROUND_TASKS_SHUTDOWN_TIMEOUT
        finished, cancelled = await wait_for_background_tasks(timeout)
        if finished:
            app.logger.info(f"Finished {finished} background task(s) before shutdown")
        if cancelled:
            app.logger.warning(
                f"Cancelled {cancelled} background task(s) still running after "
                f"{timeout} seconds (BACKGROUND_TASKS_SHUTDOWN_TIMEOUT)"
            )

    def attach_logger_sinks(self) -> None:
        """
        Attaches the loggers' sinks and the log files again after a shutdown
        removed them. Does nothing while they are attached.
        """
        app = self._app
        if app._logger_sink_ids:
            return
        for logger_component in app._loggers:
            app._logger_sink_ids.append(logger_component.configure())
        log_files_sink_id = app.log_files.attach()
        if log_files_sink_id is not None:
            app._logger_sink_ids.append(log_files_sink_id)

    def remove_logger_sinks(self) -> None:
        """Removes all logger sinks registered by this application."""
        app = self._app
        for logger_sink_id in app._logger_sink_ids:
            try:
                app.logger.remove(logger_sink_id)
            except ValueError:
                pass
        app._logger_sink_ids.clear()
        app.log_files.detach()
