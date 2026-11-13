"""
Registration of controllers, routes, CLI controllers, exception handlers,
extensions, url_for aliases and startup/shutdown methods.

Part of the Patera application object; see ``patera.patera.Patera``.
"""

# mypy: check-untyped-defs = True
from __future__ import annotations

import re
import inspect
from typing import (
    Callable,
    Type,
    TypeVar,
    cast,
)


from ..http_methods import HttpMethod
from ..utilities import (
    pascal_to_upper_snake,
)
from ..static import Static
from ..static_pages import StaticPages
from ..open_api import OpenAPIController
from ..controller import path
from ..controller import Controller
from ..exceptions import ExceptionHandler
from ..cli import CLIController
from ..injectable import Injectable
from ..base_extension import BaseExtension

from ._base import AppPart

ExtT = TypeVar("ExtT", bound=Injectable)


class Registrar(AppPart):
    """
    Registration of controllers, routes, CLI controllers, exception handlers,
    extensions, url_for aliases and startup/shutdown methods.

    Method bodies work on the application (``app``) and call its methods,
    so a Patera subclass that overrides one of them is still honoured.
    """

    def register_static_controller(self, base_path: str):
        app = self._app
        static_controller_dec = path(f"{base_path}", open_api_spec=False)
        static_controller = static_controller_dec(Static)
        app.register_controller(static_controller, with_url_prefix=False)  # type: ignore

    def register_static_pages_controller(self, base_path: str):
        app = self._app
        if not app.configs.USE_STATIC_PAGES:
            return

        static_pages_controller_dec = path(f"{base_path}", open_api_spec=False)
        static_pages_controller = static_pages_controller_dec(StaticPages)
        app.register_controller(static_pages_controller)
        app._url_for_alias[app.configs.STATIC_PAGES_CONTROLLER_NAME] = "StaticPages.get"

    def register_openapi_controller(self):
        app = self._app
        if not app.configs.OPEN_API:
            return

        openapi_controller_dec = path(app.configs.OPEN_API_URL, open_api_spec=False)
        openapi_controller = openapi_controller_dec(OpenAPIController)
        app.register_controller(openapi_controller)

    def add_extension(self, extension: Injectable):
        """
        Adds extension to extension map.
        """
        app = self._app
        name = pascal_to_upper_snake(extension.__class__.__name__)

        if app._extensions.get(name, None) is not None:
            return

        app._extensions[name] = extension

    def get_extension(self, extension_type: Type[ExtT]) -> ExtT:
        """
        Returns a registered extension by class.

        Example:
            db_manager = app.get_extension(SqlDatabaseManager)
        """
        app = self._app
        name = pascal_to_upper_snake(extension_type.__name__)
        extension = app._extensions.get(name)

        if extension is None:
            raise KeyError(f"Extension {extension_type.__name__!r} is not registered.")

        if not isinstance(extension, extension_type):
            raise TypeError(
                f"Registered extension {name!r} is not an instance of "
                f"{extension_type.__name__}."
            )

        return cast(ExtT, extension)

    def add_route_function(
        self,
        method: str,
        url_path: str,
        func: Callable,
        endpoint_name: str,
    ):
        """
        Adds the function to the Router.
        Raises DuplicateRouteError if a different handler already serves the
        same method and path.
        """
        app = self._app
        if method == HttpMethod.SOCKET.value:
            app._socket_router.add_route(url_path, func, [method], endpoint_name)
        else:
            app.router.add_route(url_path, func, [method], endpoint_name)

    def register_controller(
        self,
        *ctrls: "type[Controller]",
        with_url_prefix: bool = True,
    ):
        """
        Registers controller classes with the application. Their routes get
        the URL_PREFIX setting in front unless with_url_prefix is False.
        """
        app = self._app
        base_path: str = app.url_prefix if with_url_prefix else ""

        for ctrl in ctrls:
            dev_only: bool = getattr(ctrl, "_development", False)
            ignore: bool = getattr(ctrl, "_ignore", False)

            if ignore or (dev_only and not app.configs.DEBUG):
                continue

            ctrl_path: str | None = cast(
                str | None, getattr(ctrl, "_controller_path", None)
            )
            ctrl_open_api_spec = getattr(ctrl, "_include_open_api_spec")
            ctrl_open_api_tags = getattr(ctrl, "_open_api_tags", None)
            ctrl_alias = getattr(ctrl, "_alias", None)

            if ctrl_path is None:
                continue

            registered = app._controllers.get(ctrl.__name__)
            if registered is not None:
                if registered.__class__ is ctrl:
                    continue
                raise ValueError(
                    f"Two controllers are named {ctrl.__name__!r} "
                    f"({registered.__class__.__module__} and {ctrl.__module__}). "
                    "Endpoint names (url_for) are built from the class name, so "
                    "rename one of them."
                )

            ctrl_instance = ctrl(
                app,
                ctrl_path,
                ctrl_open_api_spec,
                ctrl_open_api_tags,
                ctrl_alias,
            )
            app.logger.info(f"Registering controller: {ctrl.__name__}")
            app._controllers[ctrl.__name__] = ctrl_instance
            app._json_spec = None

            endpoint_methods: dict[str, dict[str, str | Callable]] = (
                ctrl_instance.get_endpoint_methods()
            )

            for url_path, method in endpoint_methods.get(
                HttpMethod.SOCKET.value, {}
            ).items():
                app._check_socket_handler(
                    ctrl, cast(Callable, cast(dict, method)["method"])
                )

            for http_method, endpoints in endpoint_methods.items():
                for url_path, method in endpoints.items():
                    method_name: Callable = method["method"].__name__  # type: ignore

                    endpoint_name: str = (
                        f"{ctrl_instance.__class__.__name__}.{method_name}"
                    )

                    names: list[str] = [endpoint_name]

                    if ctrl_alias:
                        alias_name = f"{ctrl_alias}.{method_name}"
                        names.append(alias_name)

                    # "/" + "/hello" is "/hello", not "//hello".
                    rule = re.sub(
                        r"/{2,}", "/", base_path + ctrl_instance.path + url_path
                    )
                    for name in names:
                        app._add_route_function(
                            http_method,
                            rule,
                            cast(Callable, cast(dict, method)["method"]),
                            name,
                        )

    def register_cli_controller(self, ctrl: CLIController) -> None:
        app = self._app
        if not app._cli_mode:
            return
        if not getattr(ctrl, "_cli_controller", False):
            return
        if getattr(ctrl, "_ignore", False):
            return
        registered = app._cli_controllers.get(ctrl.ctrl_name)
        if registered is not None and registered is not ctrl:
            raise ValueError(
                f"CLI controller name {ctrl.ctrl_name!r} is used by both "
                f"{registered.__class__.__name__} and {ctrl.__class__.__name__}. "
                "Give one of them a different name."
            )
        app.logger.info(
            f"Registering CLI controller: {ctrl.ctrl_name} ({ctrl.__class__.__name__})"
        )
        app._cli_controllers[ctrl.ctrl_name] = ctrl

    def register_exception_handler(self, *handlers: "type[ExceptionHandler]"):
        """
        Registers exception handler classes with the application.

        A handler class that is already registered is skipped. A different
        class with the same name raises ValueError.
        """
        app = self._app

        for handler in handlers:
            registered = app._exception_handler_instances.get(handler.__name__)
            if registered is not None:
                if registered.__class__ is not handler:
                    raise ValueError(
                        f"Another exception handler named {handler.__name__!r} "
                        "is already registered."
                    )
                continue
            if not getattr(handler, "_exc_handler", False):
                continue
            if getattr(handler, "_ignore", False):
                continue
            app.logger.info(f"Registering exception handler: {handler.__name__}")
            handler_instance = handler(app)

            app._exception_handler_instances[handler_instance.__class__.__name__] = (
                handler_instance
            )

            handled_exceptions = handler_instance.get_exception_mapping()
            app._exception_handlers.update(handled_exceptions)

    def add_on_startup_method(self, func: Callable):
        """
        Adds method to on_startup collection.
        """
        app = self._app
        app._on_startup_methods.append(func)

    def add_on_shutdown_method(self, func: Callable):
        """
        Adds method to on_shutdown collection.
        """
        app = self._app
        app._on_shutdown_methods.append(func)

    def register_alias(self, alias: str, endpoint: str):
        """
        Registers an alias for an endpoint name.
        Useful for url_for lookups.
        """
        app = self._app
        app._url_for_alias[alias] = endpoint

    def register_app_extensions(self) -> None:
        """Registers application extensions."""
        app = self._app
        app_extensions = getattr(app.__class__, "app_extensions", [])

        for extension in app_extensions:
            if not inspect.isclass(extension):
                raise TypeError(
                    "Items in 'app_extensions' must be extension classes, "
                    "not instances."
                )

            if not issubclass(extension, BaseExtension):
                raise TypeError(
                    f"App extension {extension.__name__} must inherit from "
                    "BaseExtension."
                )
            if getattr(extension, "_ignore", False):
                continue
            app.app.logger.info(f"Registering app extension: {extension.__name__}")
            app._resolve_dependency(extension)
