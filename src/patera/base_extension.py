"""
Base extension class
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, cast, TypeVar, Generic
from pydantic import BaseModel

from .injectable import Injectable
from .utilities import pascal_to_upper_snake

if TYPE_CHECKING:
    from .patera import Patera

AppT = TypeVar("AppT", bound="Patera[Any]")
ConfT = TypeVar("ConfT", bound=BaseModel, default=BaseModel)


class BaseExtension(Injectable, Generic[AppT, ConfT]):
    _app: AppT

    def __init__(self, app: AppT) -> None:
        self._app = app
        self._resolve_injections()
        self._app.add_extension(self)
        self.init()

    def init(self) -> None:
        pass

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        name: str = pascal_to_upper_snake(target_type.__name__)
        value = self.app._extensions.get(name, None)
        if value is None:
            value = target_type(self.app)
            self.app._extensions[name] = value
            # self.app._extensions[target_type.__name__] = value
        return value

    def _resolve_config_var(
        self,
        config_name: str,
        declared_type: type[Any],
    ) -> Any:
        value = self.app.get_conf(config_name)

        if isinstance(value, declared_type):
            return value

        try:
            return declared_type(value)
        except Exception as exc:
            raise TypeError(
                f"Config variable {config_name!r} must be of type "
                f"{declared_type.__name__}, got {type(value).__name__}"
            ) from exc

    @property
    def app(self) -> AppT:
        if self._app is None:
            raise RuntimeError("Extension not initialized with a Patera app.")
        return cast(AppT, self._app)

    @property
    def configs(self) -> ConfT:
        """Returns the extension's configuration instance"""
        configs: ConfT = self.app.get_conf(
            self.configs_name, self.app.get_conf(self.__class__.__name__, None)
        )
        if configs is None or not isinstance(configs, BaseModel):
            raise TypeError(f"Invalid configuration for {self.__class__.__name__}")
        return configs

    @property
    def nice_name(self) -> str | None:
        """Returns nice name of the extension or None"""
        return getattr(self.configs, "NICE_NAME", None)
