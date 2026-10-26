from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import (
    Any,
    TypeVar,
    Generic,
    get_origin,
    get_args,
    Annotated,
    TypeAlias,
)

from pydantic import BaseModel, ValidationError

from .utilities import pascal_to_upper_snake
from .exceptions.runtime_exceptions import CircularDependencyError


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
            secret_key: str = ConfigVar("SECRET_KEY")

        controller.secret_key
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


# Matches string annotations that may declare an injection, e.g.
# "Inject[Database]" or "Annotated[Database, Autowire()]".
_INJECTION_RE = re.compile(r"\b(?:Inject|Annotated)\s*\[")


def _own_annotations(cls: type) -> dict[str, Any]:
    """
    Returns the annotations declared directly on ``cls``.

    Works with eagerly evaluated annotations, string annotations
    (``from __future__ import annotations``) and lazily evaluated
    annotations (Python 3.14+). Unresolvable names are returned as strings.
    """
    try:
        import annotationlib  # type: ignore[import-not-found]  # Python 3.14+
    except ImportError:
        return dict(cls.__dict__.get("__annotations__", {}))

    annotations = annotationlib.get_annotations(
        cls, format=annotationlib.Format.FORWARDREF
    )
    resolved: dict[str, Any] = {}
    for name, value in annotations.items():
        if isinstance(value, annotationlib.ForwardRef):
            value = value.__forward_arg__
        resolved[name] = value
    return resolved


def _resolve_annotation(cls: type, name: str, annotation: Any) -> Any:
    """Evaluates a string annotation in the namespace of the declaring class."""
    if not isinstance(annotation, str):
        return annotation

    module = sys.modules.get(cls.__module__)
    module_globals = dict(vars(module)) if module is not None else {}
    module_globals.setdefault("Inject", Inject)
    module_globals.setdefault("Autowire", Autowire)
    module_globals.setdefault("Annotated", Annotated)
    try:
        return eval(annotation, module_globals, dict(vars(cls)))  # noqa: S307
    except Exception as exc:
        raise TypeError(
            f"Could not resolve the injected annotation {cls.__name__}.{name}: "
            f"{annotation!r}. Injected types must be importable at runtime "
            "(not only under TYPE_CHECKING)."
        ) from exc


class Injectable:
    """
    Base class for objects that support automatic dependency injection with
    ``Inject[SomeExtension]`` (or ``Annotated[T, Autowire()]``) annotations.

    Subclasses must provide an ``app`` attribute/property returning the
    Patera application.
    """

    __autowires__: dict[str, AutowireDef] = {}
    __local_autowires__: dict[str, AutowireDef] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        inherited_autowires: dict[str, AutowireDef] = {}

        # Walk declarations in MRO order, including ordinary overrides. Merging
        # already-flattened maps can resurrect an injection suppressed by a base.
        for base in reversed(cls.__mro__[1:]):
            for name in set(vars(base)) | set(_own_annotations(base)):
                inherited_autowires.pop(name, None)
            inherited_autowires.update(base.__dict__.get("__local_autowires__", {}))

        raw_annotations = _own_annotations(cls)
        for name in set(vars(cls)) | set(raw_annotations):
            inherited_autowires.pop(name, None)

        local_autowires: dict[str, AutowireDef] = {}

        for name, raw in raw_annotations.items():
            if isinstance(raw, str):
                if not _INJECTION_RE.search(raw):
                    continue
            elif get_origin(raw) is not Annotated:
                continue

            hinted = _resolve_annotation(cls, name, raw)
            if get_origin(hinted) is not Annotated:
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

            local_autowires[name] = AutowireDef(
                name=name,
                declared_type=declared_type,
                target_type=target_type,
            )

        cls.__local_autowires__ = local_autowires
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
        """
        Returns the app-wide singleton of ``target_type``, creating (and
        registering) it on first use.
        """
        app = self.app  # type: ignore[attr-defined]
        name: str = pascal_to_upper_snake(target_type.__name__)
        value = app._extensions.get(name, None)
        if value is not None and getattr(value, "_extension_initializing", False):
            raise CircularDependencyError(
                f"Circular dependency: {target_type.__name__} is still initializing"
            )
        if value is None:
            # Types whose construction is in progress, outermost first. A type
            # that is requested again while it is being constructed is a cycle.
            resolving: list[type] = app.__dict__.setdefault(
                "_resolving_dependencies", []
            )
            if target_type in resolving:
                cycle = [*resolving[resolving.index(target_type) :], target_type]
                raise CircularDependencyError(
                    "Circular dependency: "
                    + " -> ".join(t.__name__ for t in cycle)
                    + ". Split one of the classes or inject lazily."
                )
            resolving.append(target_type)
            try:
                value = target_type(app)
            finally:
                resolving.pop()
            app._extensions[name] = value
        if not isinstance(value, target_type):
            raise TypeError(
                f"Cannot inject {target_type.__module__}.{target_type.__qualname__}: "
                f"the registry slot {name!r} holds an instance of "
                f"{type(value).__module__}.{type(value).__qualname__}. "
                "Two classes with the same name cannot both be injected."
            )
        return value

    @property
    def configs_name(self) -> str:
        """
        Return the config name used in app configurations
        for this extension.
        """
        return pascal_to_upper_snake(self.__class__.__name__)


def declared_config_model(cls: type, generic_base: type) -> type[BaseModel] | None:
    """
    Returns the configuration model declared as a type argument of
    ``generic_base`` somewhere in the class hierarchy of ``cls``.

    Example:
        class TaskManager(BaseExtension[AppT, TaskManagerConfig]): ...
        declared_config_model(MyTaskManager, BaseExtension) -> TaskManagerConfig
    """
    explicit = getattr(cls, "configs_model", None)
    if isinstance(explicit, type) and issubclass(explicit, BaseModel):
        return explicit

    for klass in cls.__mro__:
        for orig_base in getattr(klass, "__orig_bases__", ()):
            origin = get_origin(orig_base)
            if not (isinstance(origin, type) and issubclass(origin, generic_base)):
                continue
            for arg in get_args(orig_base):
                if (
                    isinstance(arg, type)
                    and issubclass(arg, BaseModel)
                    and arg is not BaseModel
                ):
                    return arg
    return None


def resolve_component_configs(component: Any, generic_base: type) -> BaseModel:
    """
    Resolves the configuration object of an extension or middleware.

    Looks up the app configuration by the component's UPPER_SNAKE_CASE name
    (falling back to its class name). Plain dictionaries (e.g. from nested
    environment variables) are validated with the declared configuration
    model, and a missing configuration falls back to the model's defaults.
    """
    app = component.app
    configs = app.get_conf(
        component.configs_name, app.get_conf(component.__class__.__name__, None)
    )
    if isinstance(configs, BaseModel):
        return configs

    model = declared_config_model(component.__class__, generic_base)

    if model is not None:
        try:
            return model.model_validate(configs if configs is not None else {})
        except ValidationError as exc:
            raise TypeError(
                f"Invalid configuration {component.configs_name!r} for "
                f"{component.__class__.__name__}: {exc}"
            ) from exc

    raise TypeError(
        f"Invalid configuration for {component.__class__.__name__}. "
        f"Add a {component.configs_name} configuration object to the app configs."
    )
