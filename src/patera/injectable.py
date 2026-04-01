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


@dataclass(slots=True)
class AutowireDef:
    name: str
    declared_type: type[Any]
    target_type: type[Any]


class Injectable:
    __autowires__: dict[str, AutowireDef] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        inherited: dict[str, AutowireDef] = {}
        for base in reversed(cls.__mro__[1:]):
            inherited.update(getattr(base, "__autowires__", {}))

        raw_annotations = cls.__dict__.get("__annotations__", {})
        if not raw_annotations:
            cls.__autowires__ = inherited
            return

        if not any(
            "Autowire" in str(a) or "Annotated" in str(a)
            for a in raw_annotations.values()
        ):
            cls.__autowires__ = inherited
            return

        hints = get_type_hints(cls, include_extras=True)
        local_defs: dict[str, AutowireDef] = {}

        for name, hinted in hints.items():
            origin = get_origin(hinted)
            if origin is not Annotated:
                continue

            declared_type, *metadata = get_args(hinted)

            autowire_meta = next(
                (m for m in metadata if isinstance(m, Autowire)),
                None,
            )
            if autowire_meta is None:
                continue

            if not isinstance(declared_type, type):
                raise TypeError(
                    f"{cls.__name__}.{name} must be annotated with a concrete class type"
                )

            target_type = autowire_meta.target or declared_type
            if not isinstance(target_type, type):
                raise TypeError(
                    f"{cls.__name__}.{name} target must resolve to a concrete class"
                )

            local_defs[name] = AutowireDef(
                name=name,
                declared_type=declared_type,
                target_type=target_type,
            )

        cls.__autowires__ = {**inherited, **local_defs}

    def _resolve_autowires(self) -> None:
        for name, definition in self.__class__.__autowires__.items():
            value = self._resolve_dependency(definition.target_type)
            setattr(self, name, value)

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        raise NotImplementedError

    @property
    def configs_name(self) -> str:
        """
        Return the config name used in app configurations
        for this extension.
        """
        return pascal_to_upper_snake(self.__class__.__name__)
