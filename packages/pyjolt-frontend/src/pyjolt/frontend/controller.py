"""Controller"""

from typing import (
    TYPE_CHECKING,
    Type,
    Optional,
    Callable,
    List,
    ParamSpec,
    TypeVar,
    Awaitable,
)

if TYPE_CHECKING:
    from .app import Application
    from .router import Route


def path(path: str):
    """
    Adds routing information to controller.
    """

    def wrapper(cls: "Type[Controller]") -> "Type[Controller]":
        setattr(cls, "__ctrl_path__", path)
        return cls

    return wrapper


P = ParamSpec("P")
R = TypeVar("R")


def page(path: str) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Adds routing information to page method"""

    def wrapper(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        page_paths = getattr(func, "__page_paths__", []) or []
        page_paths.append(path)
        setattr(func, "__page_paths__", page_paths)
        return func

    return wrapper


class Controller:
    def __init__(self, app: "Application"):
        self._app = app
        self._pages: Optional[List["Route"]] = None

    def get_pages(self) -> List["Route"]:
        ctrl_path: str = getattr(self, "__ctrl_path__", "")
        pages = []
        for name in dir(self):
            method = getattr(self, name)
            if not callable(method):
                continue
            page_paths = getattr(method, "__page_paths__", None)

            if page_paths is not None:
                for page_path in page_paths:
                    full_path: str = ctrl_path + page_path
                    route: "Route" = {
                        "path": full_path.replace("//", "/"),
                        "page": method,
                    }
                    pages.append(route)
        self._pages = pages
        return pages

    @property
    def app(self) -> "Application":
        return self._app
