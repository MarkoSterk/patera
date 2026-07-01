from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, TypeVar, overload
from patera.injectable import Injectable
from patera.utilities import pascal_to_upper_snake

from .utils import make_exposed_frontend_tool, is_frontend_tool

if TYPE_CHECKING:
    from patera import Patera
    from .frontend import Frontend

AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")
FrontendT = TypeVar("FrontendT", bound="Frontend", default="Frontend[Any]")

T = TypeVar("T", bound=Callable[..., Any])


@overload
def frontend_tool(func: T) -> T: ...
@overload
def frontend_tool(*, tool_name: Optional[str] = None) -> Callable[[T], T]: ...
def frontend_tool(
    func: T | None = None,
    *,
    tool_name: Optional[str] = None,
) -> T | Callable[[T], T]:
    """
    Marks a function/method as a frontend-exposed tool. Optionally adds a custom name
    Can be used as:
        @frontend_tool
        def my_func(...):
            ...
    or:
        @frontend_tool(tool_name="my_name")
        def my_func(...):
            ...
    """

    def decorator(target: T) -> T:
        setattr(target, "_frontend_tool", True)
        setattr(target, "_frontend_tool_name", tool_name or target.__name__)
        return target

    if func is not None:
        return decorator(func)
    return decorator


class FrontendTools(Injectable, Generic[FrontendT, AppT]):
    def __init__(self, frontend: "FrontendT"):
        self._frontend = frontend
        super().__init__()
        self._resolve_injections()

    def _get_frontend_tools(self) -> list[Callable[..., Any]]:
        tools: list[Callable[..., Any]] = []

        for attr in dir(self):
            candidate = getattr(self, attr)

            if not callable(candidate):
                continue

            if not is_frontend_tool(candidate):
                continue

            tools.append(make_exposed_frontend_tool(candidate))

        return tools

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        name: str = pascal_to_upper_snake(target_type.__name__)
        value = self.app._extensions.get(name, None)
        if value is None:
            value = target_type(self.app)
            self.app._extensions[name] = value
            # self.app._extensions[target_type.__name__] = value
        return value

    @property
    def frontend(self) -> "FrontendT":
        return self._frontend

    @property
    def app(self) -> "AppT":
        return self._frontend.app
