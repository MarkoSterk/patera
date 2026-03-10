"""Auth module"""

from typing import (
    TYPE_CHECKING,
    Optional,
    List,
    Any,
    Callable,
    TypeVar,
    ParamSpec,
    Awaitable,
)
from abc import abstractmethod

if TYPE_CHECKING:
    from .app import Application


class AuthenticationException(RuntimeError):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.status_code = 403
        self.status = "error"


class AuthorizationException(RuntimeError):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.status_code = 401
        self.status = "error"


P = ParamSpec("P")
R = TypeVar("R")


def login_required(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    setattr(func, "__login_required__", True)
    return func


def roles_required(
    required_roles: List[Any],
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        setattr(func, "__roles_required__", required_roles)
        return func

    return decorator


class Authentication:
    def __init__(self, app: "Application"):
        self._app = app

    def _check(self, page: Callable) -> None:
        required_roles: Optional[List[Any]] = getattr(page, "__role_required__", None)
        if required_roles:
            self._is_authorized(required_roles)
        if getattr(page, "__login_required__", False):
            self._is_authenticated()

    def _is_authenticated(self) -> None:
        if not self.check_user():
            raise AuthenticationException("Authentication required")

    def _is_authorized(self, required_roles: List[Any]) -> None:
        if not self.check_role(required_roles):
            raise AuthorizationException("User not authorized")

    @abstractmethod
    def check_user(self) -> bool: ...

    def check_role(self, required_roles: List[Any]) -> bool:
        return True
