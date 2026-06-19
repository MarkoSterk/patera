from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    Type,
    TypeVar,
    cast,
)

from pydantic import BaseModel

from patera.base_extension import BaseExtension
from patera.ctx import ActiveSessions, RequestContextData, get_request_context
from patera.middleware import AppCallableType, MiddlewareBase
from patera.controller import Controller

if TYPE_CHECKING:
    from patera import Patera, Request, Response
    from .sql_database import SqlDatabase


AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class SqlDatabaseManager(BaseExtension[AppT, BaseModel]):
    """
    Application-level SQL database manager.

    Responsibilities:
        - initialize configured SqlDatabase extensions
        - store database instances by db_name and class name
        - expose get_database(...)
        - register SqlDatabaseManagerMiddleware automatically
        - provide request-session commit/rollback/close helpers

    Therefore:
        - it is available in HTTP mode
        - it is available in CLI mode
        - it does not depend on the HTTP middleware chain being built
    """

    databases: list[Type["SqlDatabase[Any]"]] = []

    def init(self) -> None:
        """
        Initializes all configured SqlDatabase implementations and registers
        the request lifecycle middleware.
        """
        self._db_instances: dict[str, "SqlDatabase[Any]"] = {}

        for db_class in self.databases:
            self.app.logger.info(f"Initializing database {db_class.__name__}")

            db_instance = db_class(self.app)

            if db_instance.db_name in self._db_instances:
                raise RuntimeError(
                    f"Duplicate database name {db_instance.db_name!r}. "
                    "Database names must be unique."
                )

            self._db_instances[db_instance.db_name] = db_instance

            # Backwards-compatible direct lookup by database name.
            # Example:
            #     app.extensions["main"]
            self.app._extensions[db_instance.db_name] = db_instance
            self.app._extensions[db_instance.__class__.__name__] = db_instance

        self._register_request_middleware()

    def _register_request_middleware(self) -> None:
        """
        Registers the request lifecycle middleware.

        The middleware is not instantiated here. It is instantiated later,
        when the HTTP app is built.

        In CLI mode this registration is cheap and harmless because build()
        is not called unless the app receives ASGI traffic.
        """
        setattr(
            SqlDatabaseManagerMiddleware,
            "_sql_database_manager_name",
            self.__class__.__name__,
        )
        self.app.register_middleware(SqlDatabaseManagerMiddleware)

    def get_database(self, db_name: str) -> "SqlDatabase[AppT]":
        """
        Returns a registered database instance by database name.
        """
        db = self._db_instances.get(db_name)

        if db is None:
            raise KeyError(f"Database with name {db_name!r} does not exist.")

        return cast("SqlDatabase[AppT]", db)

    def __getitem__(self, db_name: str) -> "SqlDatabase[AppT]":
        """
        Shortcut for get_database(...).

        Example:
            db = manager["main"]
        """
        return self.get_database(db_name)

    def get_default_database(self) -> "SqlDatabase[AppT]":
        """
        Returns the default database.

        Rules:
            - if a database named 'default' exists, return it
            - if exactly one database is registered, return it
            - otherwise raise RuntimeError
        """
        if "default" in self._db_instances:
            return self.get_database("default")

        if len(self._db_instances) == 1:
            return cast("SqlDatabase[AppT]", next(iter(self._db_instances.values())))

        raise RuntimeError(
            "Cannot determine default database. "
            "Either register exactly one database or name one database 'default'."
        )

    async def commit_all_sessions(self, sessions: Optional[ActiveSessions]) -> None:
        """
        Commits all active request-bound SQLAlchemy sessions.
        """
        if sessions is None or sessions.sessions is None:
            return

        try:
            for session in list(sessions.sessions.values()):
                await session.commit()
        except Exception:
            await self.rollback_all_sessions(sessions)
            raise

    async def rollback_all_sessions(self, sessions: Optional[ActiveSessions]) -> None:
        """
        Rolls back all active request-bound SQLAlchemy sessions.

        Rollback errors are logged, but the remaining sessions are still
        processed.
        """
        if sessions is None or sessions.sessions is None:
            return

        for session in list(sessions.sessions.values()):
            try:
                await session.rollback()
            except Exception as exc:
                self.app.logger.exception(exc)

    async def close_all_sessions(self, ctx: RequestContextData) -> None:
        """
        Closes all active request-bound SQLAlchemy sessions and clears the
        request context session container.
        """
        sessions = ctx.sessions

        if sessions is None or sessions.sessions is None:
            return

        for session in list(sessions.sessions.values()):
            try:
                await session.close()
            except Exception as exc:
                self.app.logger.exception(exc)

        ctx.sessions = None

    @property
    def databases_map(self) -> dict[str, "SqlDatabase[Any]"]:
        """
        Returns registered database instances by database name.
        """
        return dict(self._db_instances)

    @property
    def databases_list(self) -> list["SqlDatabase[Any]"]:
        """
        Returns registered database instances as a list.
        """
        return list(self._db_instances.values())


class SqlDatabaseManagerMiddleware(MiddlewareBase[AppT, BaseModel]):
    """
    Request-level SQL database session lifecycle middleware.

    Responsibilities:
        - detect whether a route/controller is transactional
        - commit request sessions for successful transactional requests
        - roll back request sessions for failed transactional requests
        - defensively roll back non-transactional requests
        - close all request sessions at the end

    This middleware does not own databases.
    It delegates session lifecycle operations to SqlDatabaseManager.
    """

    __ignore__: bool = True

    _order: int = -100

    _sql_database_manager_name: str = ""

    def __init__(self, app: AppT, next_app: AppCallableType) -> None:
        super().__init__(app, next_app)
        self._manager = self._get_manager()

    def _get_manager(self) -> SqlDatabaseManager[AppT]:
        for extension in self.app.extensions.values():
            if (
                isinstance(extension, SqlDatabaseManager)
                and extension.__class__.__name__ == self._sql_database_manager_name
            ):
                return cast(SqlDatabaseManager[AppT], extension)

        raise RuntimeError(
            "SqlDatabaseManager extension is not registered. "
            "Add SqlDatabaseManager or your SqlDatabaseManager subclass "
            "to the Patera app_extensions list."
        )

    def is_transactional(self, req: "Request") -> bool:
        """
        Returns True if the controller class or route handler method is marked
        as transactional.
        """
        handler_method: Callable[..., Any] = req.route_handler
        handler: Controller = handler_method.__self__  # type: ignore[attr-defined]

        return bool(
            getattr(handler, "_transactional", False)
            or getattr(handler_method, "_transactional", False)
        )

    def is_successful_response(self, res: "Response") -> bool:
        """
        Returns True for HTTP responses that should commit transactions.
        """
        return int(res.status_code) < 400

    async def middleware(self, req: "Request") -> "Response":
        """
        Handles SQLAlchemy AsyncSession lifecycle for the current request.
        """
        ctx = get_request_context()
        is_transactional = self.is_transactional(req)

        try:
            res = await self.next(req)

            if is_transactional:
                self.app.logger.debug(
                    "Transactional request succeeded; committing SQL sessions"
                )
                await self._manager.commit_all_sessions(ctx.sessions)
            else:
                # defensive rollback of accidentally commited data
                await self._manager.rollback_all_sessions(ctx.sessions)
            return res

        except Exception as e:
            self.app.logger.debug("SQL database manager; rolling back SQL sessions")
            self.app.logger.exception(e)
            await self._manager.rollback_all_sessions(ctx.sessions)
            raise

        finally:
            await self._manager.close_all_sessions(ctx)


def transactional(
    func_or_ctrl: Callable[..., Any] | Type[Controller],
) -> Callable[..., Any] | Type[Controller]:
    """
    Marks a controller class or controller method as transactional.
    Automatically commits all sessions and rollbacks if something goes wrong.
    """
    setattr(func_or_ctrl, "_transactional", True)
    return func_or_ctrl
