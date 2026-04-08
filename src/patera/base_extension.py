"""
Base extension class
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional, cast, TypeVar, Generic
from abc import abstractmethod, ABC
from pydantic import BaseModel, ValidationError

from .injectable import Injectable

if TYPE_CHECKING:
    from .patera import Patera

AppT = TypeVar("AppT", bound="Patera")


class BaseExtension(Injectable, ABC, Generic[AppT]):
    _app: "Optional[AppT]"
    _configs: dict[str, Any]

    def __init__(self) -> None:
        self._app = None
        self._resolve_autowires()

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        value = self.app._extensions.get(target_type.__name__, None)
        if value is None:
            value = target_type()
            if hasattr(value, "init_app"):
                value.init_app(self.app)
            self.app._extensions[value.configs_name] = value
            self.app._extensions[target_type.__name__] = value
        return value

    @abstractmethod
    def init_app(self, app: AppT) -> None: ...

    def validate_configs(
        self, configs: dict[str, Any], model: type[BaseModel]
    ) -> dict[str, Any]:
        try:
            return model.model_validate(configs).model_dump()
        except ValidationError as e:
            raise ValueError(
                f"Invalid configuration for {self.configs_name}/{self.__class__.__name__}: {e}"
            ) from e

    @property
    def app(self) -> AppT:
        if self._app is None:
            raise RuntimeError("Extension not initialized with a Patera app.")
        return cast(AppT, self._app)

    @property
    def configs(self) -> dict[str, Any]:
        """Returns a dictinary of extension configs"""
        return self._configs

    @property
    def nice_name(self) -> str | None:
        """Returns nice name of the extension or None"""
        return self._configs.get("NICE_NAME", None)

    def load_configs(self) -> Optional[dict[str, Any]]:
        configs = self.app.get_conf(
            self.configs_name, self.app.get_conf(self.__class__.__name__, None)
        )
        return configs
