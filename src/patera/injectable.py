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


def ConfigVar(key: str, default: Any = None) -> Any:
    return _ConfigVar(key, default)


class _ConfigVar:
    """
    Descriptor that reads a config value through the controller instance's app.

    Example:
        class ChatController(Controller[App]):
            app_name: str = ConfigVar("SECRET_KEY")

        controller.app_name
        # internally calls:
        # controller.app.get_conf("SECRET_KEY")
    """

    def __init__(self, key: str, default: Any = None):
        self.key = key
        self.default = default
        self.name: str | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self

        if self.default is None:
            return instance.app.get_conf(self.key)

        return instance.app.get_conf(self.key, self.default)

    def __set__(self, instance: Any, value: Any) -> None:
        raise AttributeError(f"Cannot set read-only config variable '{self.name}'")


@dataclass(slots=True)
class AutowireDef:
    name: str
    declared_type: type[Any]
    target_type: type[Any]


class Injectable:
    __autowires__: dict[str, AutowireDef] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        inherited_autowires: dict[str, AutowireDef] = {}

        for base in reversed(cls.__mro__[1:]):
            inherited_autowires.update(getattr(base, "__autowires__", {}))

        raw_annotations = cls.__dict__.get("__annotations__", {})
        if not raw_annotations:
            cls.__autowires__ = inherited_autowires
            return

        if not any(
            "Autowire" in str(a) or "Annotated" in str(a)
            for a in raw_annotations.values()
        ):
            cls.__autowires__ = inherited_autowires
            return

        hints = get_type_hints(cls, include_extras=True)

        local_autowires: dict[str, AutowireDef] = {}

        for name, hinted in hints.items():
            origin = get_origin(hinted)
            if origin is not Annotated:
                continue

            declared_type, *metadata = get_args(hinted)

            autowire_meta = next(
                (m for m in metadata if isinstance(m, Autowire)),
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

        cls.__autowires__ = {**inherited_autowires, **local_autowires}

    def _resolve_autowires(self) -> None:
        for name, definition in self.__class__.__autowires__.items():
            value = self._resolve_dependency(definition.target_type)
            setattr(self, name, value)

    def _resolve_injections(self) -> None:
        """
        Resolve all supported automatic injections.
        """
        self._resolve_autowires()

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        raise NotImplementedError

    @property
    def configs_name(self) -> str:
        """
        Return the config name used in app configurations
        for this extension.
        """
        return pascal_to_upper_snake(self.__class__.__name__)
