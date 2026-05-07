from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    TypeVar,
    Generic,
    get_type_hints,
    get_origin,
    get_args,
    Annotated,
    TypeAlias,
    TYPE_CHECKING,
)

from .utilities import pascal_to_upper_snake

if TYPE_CHECKING:
    pass


T = TypeVar("T")


class Autowire(Generic[T]):
    def __init__(self, target: type[T] | None = None) -> None:
        self.target = target


Inject: TypeAlias = Annotated[T, Autowire()]


class ConfigVariable:
    """
    Runtime metadata marker used by ConfigVar.

    Example:

        some_value: ConfigVar[int, "SOME_CONFIG_NAME"]

    becomes internally:

        some_value: Annotated[int, ConfigVariable("SOME_CONFIG_NAME")]
    """

    def __init__(self, name: str) -> None:
        self.name = name


class ConfigVar:
    """
    Annotation helper for injecting configuration values.

    Usage:

        timeout: ConfigVar[int, "REQUEST_TIMEOUT"]
        secret_key: ConfigVar[str, "SECRET_KEY"]
        debug: ConfigVar[bool, "DEBUG"]

    Internally this resolves to:

        Annotated[int, ConfigVariable("REQUEST_TIMEOUT")]
    """

    def __class_getitem__(cls, params: Any) -> Any:
        if not isinstance(params, tuple) or len(params) != 2:
            raise TypeError(
                "ConfigVar[...] expects exactly two arguments: "
                'ConfigVar[type, "CONFIG_NAME"]'
            )

        declared_type, config_name = params

        if not isinstance(config_name, str):
            raise TypeError(
                "The second argument to ConfigVar must be a string literal, "
                'for example ConfigVar[int, "REQUEST_TIMEOUT"]'
            )

        return Annotated[declared_type, ConfigVariable(config_name)]


@dataclass(slots=True)
class AutowireDef:
    name: str
    declared_type: type[Any]
    target_type: type[Any]


@dataclass(slots=True)
class ConfigVarDef:
    name: str
    declared_type: type[Any]
    config_name: str


class Injectable:
    __autowires__: dict[str, AutowireDef] = {}
    __config_vars__: dict[str, ConfigVarDef] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        inherited_autowires: dict[str, AutowireDef] = {}
        inherited_config_vars: dict[str, ConfigVarDef] = {}

        for base in reversed(cls.__mro__[1:]):
            inherited_autowires.update(getattr(base, "__autowires__", {}))
            inherited_config_vars.update(getattr(base, "__config_vars__", {}))

        raw_annotations = cls.__dict__.get("__annotations__", {})
        if not raw_annotations:
            cls.__autowires__ = inherited_autowires
            cls.__config_vars__ = inherited_config_vars
            return

        if not any(
            "Autowire" in str(a)
            or "Annotated" in str(a)
            or "ConfigVar" in str(a)
            or "ConfigVariable" in str(a)
            for a in raw_annotations.values()
        ):
            cls.__autowires__ = inherited_autowires
            cls.__config_vars__ = inherited_config_vars
            return

        hints = get_type_hints(cls, include_extras=True)

        local_autowires: dict[str, AutowireDef] = {}
        local_config_vars: dict[str, ConfigVarDef] = {}

        for name, hinted in hints.items():
            origin = get_origin(hinted)
            if origin is not Annotated:
                continue

            declared_type, *metadata = get_args(hinted)

            autowire_meta = next(
                (m for m in metadata if isinstance(m, Autowire)),
                None,
            )

            config_var_meta = next(
                (m for m in metadata if isinstance(m, ConfigVariable)),
                None,
            )

            if autowire_meta is not None:
                if not isinstance(declared_type, type):
                    raise TypeError(
                        f"{cls.__name__}.{name} must be annotated with a concrete class type"
                    )

                target_type = autowire_meta.target or declared_type
                if not isinstance(target_type, type):
                    raise TypeError(
                        f"{cls.__name__}.{name} target must resolve to a concrete class"
                    )

                local_autowires[name] = AutowireDef(
                    name=name,
                    declared_type=declared_type,
                    target_type=target_type,
                )

            if config_var_meta is not None:
                if not isinstance(declared_type, type):
                    raise TypeError(
                        f"{cls.__name__}.{name} must be annotated with a concrete config value type"
                    )

                local_config_vars[name] = ConfigVarDef(
                    name=name,
                    declared_type=declared_type,
                    config_name=config_var_meta.name,
                )

        cls.__autowires__ = {**inherited_autowires, **local_autowires}
        cls.__config_vars__ = {**inherited_config_vars, **local_config_vars}

    def _resolve_autowires(self) -> None:
        for name, definition in self.__class__.__autowires__.items():
            value = self._resolve_dependency(definition.target_type)
            setattr(self, name, value)

    def _resolve_config_vars(self) -> None:
        for name, definition in self.__class__.__config_vars__.items():
            value = self._resolve_config_var(
                config_name=definition.config_name,
                declared_type=definition.declared_type,
            )
            setattr(self, name, value)

    def _resolve_injections(self) -> None:
        """
        Resolve all supported automatic injections.
        """
        self._resolve_autowires()
        self._resolve_config_vars()

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        raise NotImplementedError

    def _resolve_config_var(
        self,
        config_name: str,
        declared_type: type[Any],
    ) -> Any:
        raise NotImplementedError

    @property
    def configs_name(self) -> str:
        """
        Return the config name used in app configurations
        for this extension.
        """
        return pascal_to_upper_snake(self.__class__.__name__)
