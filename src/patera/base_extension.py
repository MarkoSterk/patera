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
        self._resolve_injections()
        self._app.add_extension(self)
        self.init()

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
