"""
Base extension class
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, cast, TypeVar, Generic
from pydantic import BaseModel

from .injectable import Injectable, resolve_component_configs

if TYPE_CHECKING:
    from .patera import Patera

AppT = TypeVar("AppT", bound="Patera[Any]")
ConfT = TypeVar("ConfT", bound=BaseModel, default=BaseModel)


class BaseExtension(Injectable, Generic[AppT, ConfT]):
    _app: AppT

    def __init__(self, app: AppT) -> None:
        self._app = app
        # Initialization is synchronous. Roll back framework registrations,
        # including nested dependencies, if any part of construction fails.
        registrations = (
            "_extensions",
            "_middleware_classes",
            "_controllers",
            "_cli_controllers",
            "_exception_handlers",
            "_exception_handler_instances",
            "_on_startup_methods",
            "_on_shutdown_methods",
            "_request_observers",
            "_all_templates_paths",
            "_template_prefix_loaders",
            "_url_for_alias",
        )
        snapshots = {
            name: value.copy()
            for name in registrations
            if isinstance(value := getattr(app, name, None), (dict, list))
        }
        routers = {
            name: getattr(app, name).copy() for name in ("_router", "_socket_router")
        }
        json_spec = app._json_spec
        self._extension_initializing = True
        try:
            self._resolve_injections()
            self._app.add_extension(self)
            self.init()
        except BaseException:
            for name, snapshot in snapshots.items():
                current = getattr(app, name)
                current.clear()
                if isinstance(current, dict):
                    current.update(snapshot)
                else:
                    current.extend(snapshot)
            for name, router in routers.items():
                setattr(app, name, router)
            app._json_spec = json_spec
            raise
        finally:
            self._extension_initializing = False

    def init(self) -> None:
        pass

    @property
    def app(self) -> AppT:
        if self._app is None:
            raise RuntimeError("Extension not initialized with a Patera app.")
        return cast(AppT, self._app)

    @property
    def configs(self) -> ConfT:
        """
        Returns the extension's configuration instance.

        The configuration is looked up by the extension's UPPER_SNAKE_CASE
        class name. Dictionaries are validated with the declared config model
        and a missing configuration falls back to the model's defaults.
        """
        cached = self.__dict__.get("_resolved_configs")
        if cached is None:
            cached = resolve_component_configs(self, BaseExtension)
            self.__dict__["_resolved_configs"] = cached
        return cast(ConfT, cached)

    @property
    def nice_name(self) -> str | None:
        """Returns nice name of the extension or None"""
        return getattr(self.configs, "NICE_NAME", None)
