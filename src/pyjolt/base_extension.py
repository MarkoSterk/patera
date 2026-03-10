"""
Base extension class
"""

from typing import TYPE_CHECKING, Any, Optional, cast
from abc import abstractmethod, ABC
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from .pyjolt import PyJolt


class BaseExtension(ABC):
    _configs_name: str
    _app: "Optional[PyJolt]"
    _configs: dict[str, Any]

    @abstractmethod
    def init_app(self, app: "PyJolt") -> None: ...

    def validate_configs(
        self, configs: dict[str, Any], model: type[BaseModel]
    ) -> dict[str, Any]:
        try:
            return model.model_validate(configs).model_dump()
        except ValidationError as e:
            raise ValueError(
                f"Invalid configuration for {self._configs_name or self.__class__.__name__}: {e}"
            ) from e

    @property
    def configs_name(self) -> str:
        """
        Return the config name used in app configurations
        for this extension.
        """
        return self._configs_name

    @property
    def app(self) -> "PyJolt":
        if self._app is None:
            raise RuntimeError("Extension not initialized with a PyJolt app.")
        return cast("PyJolt", self._app)

    @property
    def configs(self) -> dict[str, Any]:
        """Returns a dictinary of extension configs"""
        return self._configs

    @property
    def nice_name(self) -> str | None:
        """Returns nice name of the extension or None"""
        return self._configs.get("NICE_NAME", None)
