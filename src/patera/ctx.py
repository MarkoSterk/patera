# patera/ctx.py
from __future__ import annotations

from contextvars import ContextVar, Token
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .patera import Patera
    from .request import Request
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ActiveSessions:
    sessions: Optional[Dict[str, "AsyncSession"]] = None

    def get_session(self, session_name: str) -> "AsyncSession | None":
        if self.sessions is None:
            return None
        return self.sessions.get(session_name, None)

    def set_session(self, session_name: str, session: "AsyncSession") -> None:
        if self.sessions is None:
            self.sessions = {}
        self.sessions[session_name] = session

    def remove_session(self, session_name: str) -> None:
        if self.sessions is None:
            return
        self.sessions.pop(session_name, None)
        if not self.sessions:
            self.sessions = None


@dataclass
class RequestContextData:
    app: Optional["Patera"] = None
    request: Optional["Request"] = None
    sessions: Optional[ActiveSessions] = None
    controller: Optional[Any] = None
    user: Optional[Any] = None
    extras: dict[str, Any] = field(default_factory=dict)


_current_context: ContextVar[Optional[RequestContextData]] = ContextVar(
    "patera_current_context",
    default=None,
)


class CurrentContextProxy:
    def _ctx(self) -> RequestContextData:
        ctx = _current_context.get()
        if ctx is None:
            raise RuntimeError(
                "No active request context. This can only be used during a request."
            )
        return ctx

    @property
    def app(self):
        value = self._ctx().app
        if value is None:
            raise RuntimeError("No app.")
        return value

    @property
    def request(self):
        value = self._ctx().request
        if value is None:
            raise RuntimeError("No request.")
        return value

    @property
    def sessions(self) -> ActiveSessions:
        value = self._ctx().sessions
        if value is None:
            raise RuntimeError("No current database sessions.")
        return value

    def session(self, session_name: str):
        sessions = self._ctx().sessions
        if sessions is None:
            raise RuntimeError("No current database sessions.")
        session = sessions.get_session(session_name)
        if session is None:
            raise RuntimeError(
                f"No active database session named '{session_name}' in current request context."
            )
        return session

    @property
    def controller(self):
        return self._ctx().controller

    @property
    def user(self):
        return self._ctx().user

    @user.setter
    def user(self, value):
        self._ctx().user = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._ctx().extras.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._ctx().extras[key] = value


current_request = CurrentContextProxy()


def has_request_context() -> bool:
    return _current_context.get() is not None


def get_request_context() -> RequestContextData:
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("No active request context.")
    return ctx


@contextmanager
def request_context(*, app=None, request=None, controller=None) -> Any:
    ctx = RequestContextData(
        app=app,
        request=request,
        controller=controller,
    )
    token: Token = _current_context.set(ctx)
    try:
        yield ctx
    finally:
        _current_context.reset(token)


@contextmanager
def bind_context_value(name: str, value: Any):
    ctx = get_request_context()
    previous = getattr(ctx, name)
    setattr(ctx, name, value)
    try:
        yield
    finally:
        setattr(ctx, name, previous)


@contextmanager
def bind_session(session_name: str, session: "AsyncSession"):
    ctx = get_request_context()

    if ctx.sessions is None:
        ctx.sessions = ActiveSessions()

    previous = ctx.sessions.get_session(session_name)
    ctx.sessions.set_session(session_name, session)

    try:
        yield
    finally:
        if previous is None:
            ctx.sessions.remove_session(session_name)
            if ctx.sessions.sessions is None:
                ctx.sessions = None
        else:
            ctx.sessions.set_session(session_name, previous)
