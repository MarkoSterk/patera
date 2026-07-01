import os
from dataclasses import dataclass
from typing import (
    Annotated,
    Callable,
    Type,
    TypeAlias,
    TypeVar,
    Generic,
    cast,
    Any,
    get_type_hints,
    get_origin,
    get_args,
)
from patera import Patera, BaseExtension
import webview

AppT = TypeVar("AppT", bound="Patera[Any]")

T = TypeVar("T")


class AutoExpose(Generic[T]):
    def __init__(self, target: type[T] | None = None) -> None:
        self.target = target


Expose: TypeAlias = Annotated[T, AutoExpose()]

INTERFACE_BASE_URL: str = "/_frontend"
INTERFACE_CONTROLLER_ALIAS: str = "frontend"


@dataclass(slots=True)
class ExposeDef:
    name: str
    declared_type: type[Any]
    target_type: type[Any]


class Frontend(BaseExtension[AppT], Generic[AppT]):
    __exposes__: dict[str, ExposeDef] = {}

    def __init__(self, app: AppT) -> None:
        self._window: webview.Window = cast(webview.Window, None)
        self._active_windows: list[webview.Window] = []
        self._exposed_tools: list[Callable[..., Any]] = []
        self._exposed_tools_map: dict[str, Callable] = {}
        self._desktop_root_path: str = os.path.dirname(__file__)
        super().__init__(app)
        self._resolve_exposes()
        self._register_interface_controller()

    def _register_interface_controller(self) -> None:
        from .frontend_interface_controller import _FrontendInterfaceController
        from patera.controller import path

        ctrl_dec = path(
            INTERFACE_BASE_URL, alias=INTERFACE_CONTROLLER_ALIAS, open_api_spec=False
        )
        ctrl: Type[_FrontendInterfaceController] = ctrl_dec(
            _FrontendInterfaceController
        )
        self.app.register_controller(ctrl)
        ctrl_path = getattr(ctrl, "_controller_path")
        ctrl_instance: _FrontendInterfaceController = self._app._controllers.get(
            ctrl_path
        )  # type: ignore
        ctrl_instance.frontend = self

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        inherited_exposes: dict[str, ExposeDef] = {}

        for base in reversed(cls.__mro__[1:]):
            inherited_exposes.update(getattr(base, "__exposes__", {}))

        raw_annotations = cls.__dict__.get("__annotations__", {})
        if not raw_annotations:
            cls.__exposes__ = inherited_exposes
            return

        if not any(
            "Expose" in str(a) or "Annotated" in str(a)
            for a in raw_annotations.values()
        ):
            cls.__exposes__ = inherited_exposes
            return

        hints = get_type_hints(cls, include_extras=True)

        local_exposes: dict[str, ExposeDef] = {}

        for name, hinted in hints.items():
            origin = get_origin(hinted)
            if origin is not Annotated:
                continue

            declared_type, *metadata = get_args(hinted)

            expose_meta = next(
                (m for m in metadata if isinstance(m, AutoExpose)),
                None,
            )

            if expose_meta is not None:
                if not isinstance(declared_type, type):
                    raise TypeError(
                        f"{cls.__name__}.{name} must be annotated with a concrete class type"
                    )

                target_type = expose_meta.target or declared_type
                if not isinstance(target_type, type):
                    raise TypeError(
                        f"{cls.__name__}.{name} target must resolve to a concrete class"
                    )

                local_exposes[name] = ExposeDef(
                    name=name,
                    declared_type=declared_type,
                    target_type=target_type,
                )

        cls.__exposes__ = {**inherited_exposes, **local_exposes}

    def _resolve_exposes(self) -> None:
        """
        Resolve all supported automatic exposes.
        """
        for name, definition in self.__class__.__exposes__.items():
            value = definition.target_type(self)
            setattr(self, name, value)
            self._exposed_tools = [*self._exposed_tools, *value._get_frontend_tools()]
        self._exposed_tools_map = {
            getattr(func, "_frontend_tool_name", getattr(func, "__name__")): func
            for func in self._exposed_tools
        }

    @property
    def exposed_tools(self) -> list[Callable]:
        return self._exposed_tools

    @property
    def exposed_tools_map(self) -> dict[str, Callable]:
        return self._exposed_tools_map

    @property
    def root_path(self) -> str:
        return self._desktop_root_path
