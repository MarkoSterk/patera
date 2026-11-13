"""
Finds and registers the application's components (controllers, CLI
controllers, exception handlers, middleware and loggers) by scanning
the app's folders.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

import importlib
import importlib.metadata
import inspect
from pathlib import Path
from typing import (
    List,
    Type,
)


from ..utilities import (
    find_python_files_by_name,
)
from ..controller import Controller
from ..exceptions import ExceptionHandler
from ..middleware import MiddlewareBase
from ..cli import CLIController
from ..logging.logger_config_base import LoggerBase

from ._base import AppPart


class ModuleLoader(AppPart):
    """
    Finds and registers the application's components (controllers, CLI
    controllers, exception handlers, middleware and loggers) by scanning
    the app's folders.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    def load_controllers_exc_handlers_middleware(self, cli_mode: bool = False) -> None:
        app = self._app
        logger_folders: list[str] = ["logging", "loggers"]
        logger_folders.extend(app._configs.LOGGER_FOLDERS or [])

        app._load_detected_modules_once(
            logger_folders,
            ["logger", "log_sink", "logging"],
            LoggerBase,
        )

        cli_controller_folders: list[str] = ["cli", "cli_controllers", "clis"]
        cli_controller_folders.extend(app._configs.CLI_CONTROLLER_FOLDERS or [])

        app._load_detected_modules_once(
            cli_controller_folders,
            ["cli", "cli_controller"],
            CLIController,
        )

        if cli_mode:
            return

        controller_folders: list[str] = [
            "api",
            "public",
            "controllers",
            "routers",
            "routes",
        ]
        controller_folders.extend(app._configs.CONTROLLER_FOLDERS or [])

        app._load_detected_modules_once(
            controller_folders,
            ["api", "controller", "public", "router", "routes"],
            Controller,
        )

        exception_handler_folders: list[str] = ["exceptions", "exc_controllers"]
        exception_handler_folders.extend(app._configs.EXCEPTION_HANDLER_FOLDERS or [])

        app._load_detected_modules_once(
            exception_handler_folders,
            ["handler", "exception_controller", "controller"],
            ExceptionHandler,
        )

        middleware_folders: list[str] = ["middleware", "middlewares"]
        middleware_folders.extend(app._configs.MIDDLEWARE_FOLDERS or [])

        app._load_detected_modules_once(
            middleware_folders,
            ["middleware", "mw"],
            MiddlewareBase,
        )

    def unique_list(self, values: list[str]) -> list[str]:
        """
        Returns a list with duplicates removed while preserving order.
        """
        return list(dict.fromkeys(values))

    def load_detected_modules_once(
        self,
        folders: list[str],
        name_patterns: list[str],
        load_class: Type,
    ) -> None:
        """
        Scans folders for matching Python files and loads each discovered file only once.
        This protects against duplicate default/configured folders and overlapping scans.
        """
        app = self._app
        app_root: Path = Path(app._root_path)
        loaded_files: set[Path] = set()

        for folder in app._unique_list(folders):
            folder_path = app_root / folder
            files = find_python_files_by_name(folder_path, name_patterns)

            unique_files: list[Path] = []
            for file in files:
                resolved_file = file.resolve()
                if resolved_file in loaded_files:
                    continue
                loaded_files.add(resolved_file)
                unique_files.append(file)
            app._load_detected_module(unique_files, load_class)

    def load_detected_module(self, file_paths: List[Path], load_class: Type) -> None:
        """
        Tries to load implementations:
            - controllers
            - CLI controllers
            - exception handlers
            - middleware
            - loggers
        """
        app = self._app
        app_root = Path(app._root_path)
        root_package = app_root.name
        for file_path in file_paths:
            relative_path = file_path.relative_to(app_root)
            module_path = relative_path.with_suffix("")
            import_path = f"{root_package}.{'.'.join(module_path.parts)}"

            module = importlib.import_module(import_path)

            for _, obj in inspect.getmembers(
                module,
                lambda _obj: inspect.isclass(_obj) and issubclass(_obj, load_class),
            ):
                ignore: bool = getattr(obj, "_ignore", False)
                dev_only: bool = getattr(obj, "_development", False)

                if ignore or (dev_only and not app._configs.DEBUG):
                    continue

                if (
                    issubclass(obj, Controller)
                    and obj is not Controller
                    and getattr(obj, "_controller_path", None) is not None
                ):
                    app.register_controller(obj)
                    continue

                if (
                    issubclass(obj, CLIController)
                    and obj is not CLIController
                    and getattr(obj, "_cli_controller", False)
                ):
                    obj_inst = obj(app)
                    app.register_cli_controller(obj_inst)
                    continue

                if (
                    issubclass(obj, MiddlewareBase)
                    and obj is not MiddlewareBase
                    and getattr(obj, "_middleware", False)
                ):
                    app.register_middleware(obj)
                    continue

                if (
                    issubclass(obj, ExceptionHandler)
                    and obj is not ExceptionHandler
                    and getattr(obj, "_exc_handler", False)
                ):
                    app.register_exception_handler(obj)
                    continue

                if (
                    issubclass(obj, LoggerBase)
                    and obj is not LoggerBase
                    and getattr(obj, "_logger", False)
                ):
                    # A logger class imported into a second module must not
                    # add a second sink.
                    if obj in app._registered_loggers:
                        continue
                    app._registered_loggers.add(obj)
                    app.logger.info(f"Registering logger sink: {obj.__name__}")
                    logger_component = obj(app)
                    app._loggers.append(logger_component)
                    app._logger_sink_ids.append(logger_component.configure())
                    continue
