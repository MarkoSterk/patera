from __future__ import annotations

from typing import TypeVar, Any, TYPE_CHECKING, Optional, Type, Callable, cast

from patera import Patera, Request, Response
from patera.ctx import get_request_context, ActiveSessions, RequestContextData
from patera.middleware import MiddlewareBase, AppCallableType
from patera.controller import Controller

if TYPE_CHECKING:
    from .sql_database import SqlDatabase


AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class SqlDatabaseManager(MiddlewareBase[AppT]):
    """
    Middleware-managed SQL database session lifecycle.

    Non-transactional requests:
        - sessions may be opened lazily
        - sessions are closed at the end
        - uncommitted work is rolled back defensively

    Transactional requests:
        - sessions are committed on successful response
        - sessions are rolled back on errors or unsuccessful response
        - sessions are always closed

    Default middleware order for SqlDatabaseManager is -100
    """

    __ignore__: bool = True

    _order: int = -100

    databases: list[Type["SqlDatabase[Any]"]] = []

    def __init__(self, app: AppT, next_app: AppCallableType) -> None:
        super().__init__(app, next_app)
        self._db_instances: dict[str, "SqlDatabase[Any]"] = {}
        for db in self.databases:
            self.app.logger.info(f"Initializing database {db.__name__}")
            db_inst = db(self.app)
            self._db_instances[db_inst.db_name] = db_inst

    def get_database(self, db_name: str) -> "SqlDatabase[AppT]":
        db = self._db_instances.get(db_name)
        if db is None:
            raise KeyError(f"Database with name {db_name!r} does not exist.")
        return cast("SqlDatabase[AppT]", db)

    async def commit_all_sessions(self, sessions: Optional[ActiveSessions]) -> None:
        if sessions is None or sessions.sessions is None:
            return
        try:
            for session in list(sessions.sessions.values()):
                await session.commit()
        except Exception:
            await self.rollback_all_sessions(sessions)
            raise

    async def rollback_all_sessions(self, sessions: Optional[ActiveSessions]) -> None:
        if sessions is None or sessions.sessions is None:
            return
        for session in list(sessions.sessions.values()):
            try:
                await session.rollback()
            except Exception as exc:
                self.app.logger.exception(exc)

    async def close_all_sessions(self, ctx: RequestContextData) -> None:
        sessions = ctx.sessions
        if sessions is None or sessions.sessions is None:
            return
        for session in list(sessions.sessions.values()):
            try:
                await session.close()
            except Exception as exc:
                self.app.logger.exception(exc)
        ctx.sessions = None

    def is_transactional(self, req: Request) -> bool:
        handler_method: Callable[..., Any] = req.route_handler
        handler: Controller = handler_method.__self__  # type: ignore[attr-defined]

        return bool(
            getattr(handler, "_transactional", False)
            or getattr(handler_method, "_transactional", False)
        )

    async def middleware(self, req: Request) -> Response:
        """
        Handles SQLAlchemy AsyncSession lifecycle for the current request.
        """
        ctx = get_request_context()
        is_transactional = self.is_transactional(req)

        try:
            self.app.logger.debug("Database manager before...")
            res = await self.next(req)
            if is_transactional:
                self.app.logger.debug(
                    "Database manager transactional, commiting sessions"
                )
                await self.commit_all_sessions(ctx.sessions)
            else:
                # Defensive rollback for non-transactional routes.
                # This discards accidental pending changes.
                self.app.logger.debug(
                    "Database manager defensive rollback (non-transactional)"
                )
                await self.rollback_all_sessions(ctx.sessions)
            return res
        except Exception:
            self.app.logger.debug("Database manager exception block rollback")
            await self.rollback_all_sessions(ctx.sessions)
            raise
        finally:
            self.app.logger.debug("Database manager finally block session closure")
            await self.close_all_sessions(ctx)


def transactional(
    func_or_ctrl: Callable[..., Any] | Type[Controller],
) -> Callable[..., Any] | Type[Controller]:
    """
    Marks a controller class or controller method as transactional.

    If the request completes successfully, all request-scoped SQL sessions
    are committed. If an exception occurs or an unsuccessful response is
    returned, all sessions are rolled back.
    """
    setattr(func_or_ctrl, "_transactional", True)
    return func_or_ctrl
