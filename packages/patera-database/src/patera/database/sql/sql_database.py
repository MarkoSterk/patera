"""
sql_database.py
Module for sql database connection/integration
"""

import inspect as py_inspect
from typing import (
    ClassVar,
    Any,
    Dict,
    Optional,
    Callable,
    Tuple,
    Type,
    cast,
    TYPE_CHECKING,
    TypeVar,
    Generic,
)
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import wraps
from sqlalchemy import MetaData, Table, event, select, func
from sqlalchemy.inspection import inspect
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from pydantic import BaseModel, Field, ConfigDict
from .dialect_overview_extras import (
    _portable_schema_stats,
    _extras_postgres,
    _extras_sqlite,
    _extras_mysql,
    _extras_mssql,
    _extras_oracle,
)

# pylint: disable-next=E0402
from patera.utilities import run_sync_or_async
from patera.ctx import (
    ActiveSessions,
    bind_session,
    child_context,
    get_request_context,
    has_request_context,
    request_context,
)
from patera.cli import CLIController

# pylint: disable-next=E0402
from patera.base_extension import BaseExtension
from .declarative_base import DeclarativeBaseModel
from .request_keys import TRANSACTION_OPEN

if TYPE_CHECKING:
    from patera import Patera


class SqlDatabaseConfig(BaseModel):
    """Configuration options for SqlDatabase extension"""

    model_config = ConfigDict(extra="allow")

    DATABASE_URI: str = Field(description="Connection string for the database")
    DATABASE_SESSION_NAME: str = Field(
        "session",
        description=(
            "Name under which this database's request-bound AsyncSession is "
            "stored in the request context (current_request.session(name)). "
            "Must be unique per database when using multiple databases."
        ),
    )
    SHOW_SQL: bool = Field(
        False,
        description="If True, every executed SQL statement is logged to the console.",
    )
    NICE_NAME: Optional[str] = Field(
        None,
        description="Name of the database for admin dashboard view. Defaults to db_name variable.",
    )
    EXPIRE_ON_COMMIT: bool = Field(
        False,
        description="Wether session should expire upon commit or not. Defaults to False.",
    )
    AUTOFLUSH: bool = Field(
        False, description="Wether session should autoflush or not. Defaults to False."
    )
    SQLITE_FOREIGN_KEYS: bool = Field(
        False,
        description=(
            "SQLite only: run PRAGMA foreign_keys=ON on every new connection, so "
            "FOREIGN KEY constraints (ON DELETE CASCADE, RESTRICT, ...) are "
            "enforced. SQLite leaves them off by default. Ignored for other "
            "databases, which always enforce them."
        ),
    )
    SQLITE_BUSY_TIMEOUT: Optional[float] = Field(
        None,
        ge=0,
        description=(
            "SQLite only: seconds a connection waits for another connection's "
            "lock before failing with 'database is locked' (PRAGMA "
            "busy_timeout on every new connection). None keeps the driver's "
            "default of 5 seconds or a ?timeout= in DATABASE_URI; a value "
            "here takes precedence over both. Ignored for other databases."
        ),
    )


def _sqlite_connection_hook(
    foreign_keys: bool, busy_timeout: Optional[float]
) -> Optional[Callable[[Any, Any], None]]:
    """
    A hook that applies the SQLite settings to every new connection, or
    None when none are set. SQLite keeps both settings per connection.
    """
    pragmas: list[str] = []
    if foreign_keys:
        pragmas.append("PRAGMA foreign_keys=ON")
    if busy_timeout is not None:
        pragmas.append(f"PRAGMA busy_timeout={round(busy_timeout * 1000)}")
    if not pragmas:
        return None

    def configure(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for pragma in pragmas:
                cursor.execute(pragma)
        finally:
            cursor.close()

    return configure


_DIALECT_EXTRAS: Dict[str, Callable] = {
    "postgresql": _extras_postgres,
    "sqlite": _extras_sqlite,
    "mysql": _extras_mysql,
    "mariadb": _extras_mysql,
    "mssql": _extras_mssql,
    "oracle": _extras_oracle,
}

AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class SqlDatabase(BaseExtension[AppT, SqlDatabaseConfig], Generic[AppT]):
    """
    A simple async Database interface using SQLAlchemy.
    """

    __db_name__: ClassVar[str]

    def init(self) -> None:
        """
        Initializes the database interface
        app.get_conf("DATABASE_URI") must return a connection string like:
        "postgresql+asyncpg://user:pass@localhost/dbname"
        or "sqlite+aiosqlite:///./patera.db"
        """
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._db_uri: str = ""
        self._session_name: str
        self._db_uri = self.configs.DATABASE_URI
        self._session_name = self.configs.DATABASE_SESSION_NAME
        self._app.add_on_startup_method(self.connect)
        self._app.add_on_shutdown_method(self.disconnect)
        # the SqlDatabase instance is stored in app._extensions with key as db_name for later retrieval in session decorators and elsewhere
        # in addition to the standard classname and config name storage
        self.app._extensions[self.db_name] = self

        # If the SqlDatabase class inherits from patera.migrate.Migrate class
        if "migrate" in [cl.__name__.lower() for cl in self.__class__.mro()]:
            from patera.migrate import Migrate  # type: ignore

            self._migrate = Migrate(self._app, self)

    async def connect(self) -> None:
        """
        Creates the async engine and session factory.
        Runs automatically when the lifespan.start signal is received
        """
        if not self._engine:
            self._engine = create_async_engine(
                cast(str, self._db_uri),
                echo=self.configs.SHOW_SQL,
                pool_pre_ping=True,
                pool_recycle=1800,
            )
            if self._engine.dialect.name == "sqlite":
                hook = _sqlite_connection_hook(
                    self.configs.SQLITE_FOREIGN_KEYS, self.configs.SQLITE_BUSY_TIMEOUT
                )
                if hook is not None:
                    event.listen(self._engine.sync_engine, "connect", hook)
        self.app.logger.info(f"Connecting to database {self.__class__.__name__}")
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=self.configs.EXPIRE_ON_COMMIT,
            autoflush=self.configs.AUTOFLUSH,
        )

    async def disconnect(self) -> None:
        """
        Runs automatically when the lifespan.shutdown signal is received
        """
        if self._engine:
            self.app.logger.info(
                f"Disconnecting from database {self.__class__.__name__}"
            )
            await self._engine.dispose()
            self._engine = None
        # Sessions made from the old factory would open connections on the
        # disposed engine that nothing closes; the next use reconnects.
        self._session_factory = None

    def create_session(self) -> AsyncSession:
        """
        Creates new session and returns session object. Used for manual session handling.

        WARNING: You must close the session manually after use with await session.close()
        or use it within an async with block.
        """
        if self._session_factory is not None:
            return cast(AsyncSession, self._session_factory())
        # pylint: disable-next=W0719
        raise RuntimeError(
            "Database is not connected. "
            "Connection should be established automatically. "
            "Please check network connection and configurations."
        )

    async def execute_raw(
        self, statement, *, as_transaction: bool = False
    ) -> list[RowMapping]:
        """
        Executes raw sql statement and returns list of RowMapping objects.

        If as_transaction is True, the execution will be wrapped in a transaction.
        as_transaction=False is for read-only state,emts; DML
        """
        if not self._session_factory:
            raise RuntimeError("Database is not connected.")
        async with self._session_factory() as session:
            if as_transaction:
                async with session.begin():
                    result = await session.execute(statement)
            else:
                result = await session.execute(statement)
            return cast(list[RowMapping], result.mappings().all())

    async def count_tables(self, schema: str | None = None) -> int:
        if self._engine is None:
            return 0
        async with self._engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: len(inspect(sync_conn).get_table_names(schema=schema))
            )

    async def count_rows_exact(
        self, schema: str | None = None
    ) -> Tuple[Dict[str, int], int]:
        """
        Returns (per_table_counts, total_rows). Counts are exact but can be slow.
        """
        if self._engine is None:
            raise Exception("Missing engine for database: ", self.__class__.__name__)
        async with self._engine.connect() as aconn:

            def _work(sync_conn) -> Tuple[Dict[str, int], int]:
                insp = inspect(sync_conn)
                table_names = insp.get_table_names(schema=schema)

                md = MetaData()
                per_table: Dict[str, int] = {}
                total = 0

                for name in table_names:
                    t = Table(name, md, schema=schema, autoload_with=sync_conn)
                    cnt = sync_conn.execute(
                        select(func.count()).select_from(t)
                    ).scalar_one()
                    full = f"{schema}.{name}" if schema else name
                    per_table[full] = int(cnt)
                    total += int(cnt)

                return per_table, total

            return await aconn.run_sync(_work)

    async def collect_db_overview(
        self, schema: str | None = None, with_extras: bool = True
    ) -> Dict[str, Any]:
        """
        Portable overview across dialects, with optional per-dialect extras.
        """
        if self._engine is None:
            raise Exception("Missing engine for database: ", self.__class__.__name__)
        async with self._engine.connect() as aconn:

            def _work(sync_conn):
                data = _portable_schema_stats(sync_conn, schema=schema)
                if with_extras:
                    dname = sync_conn.dialect.name
                    extras_fn = _DIALECT_EXTRAS.get(dname)
                    if extras_fn:
                        try:
                            data["extras"] = extras_fn(sync_conn)
                        except Exception:
                            # Don't break the dashboard if extras fail
                            data["extras"] = {"error": f"{dname} extras unavailable"}
                return data

            return await aconn.run_sync(_work)

    @property
    def db_uri(self):
        """
        Returns database connection uri string
        """
        return self._db_uri

    @property
    def engine(self) -> AsyncEngine:
        """
        Returns database engine
        """
        if self._engine is None:
            raise RuntimeError("Engine not initialized. Call connect() first.")
        return cast(AsyncEngine, self._engine)

    @property
    def session_name(self) -> str:
        """
        Returns the session variable name to be used in the kwargs of the request handler.
        Default is "session", can be changed via configuration.
        """
        return self._session_name

    @property
    def db_name(self) -> str:
        return getattr(self, "__db_name__", None) or self.__class__.__name__.lower()

    @property
    def nice_name(self) -> str:
        return self.configs.NICE_NAME or self.db_name

    @property
    def database_uri(self) -> str:
        return self.configs.DATABASE_URI

    @property
    def models_list(self) -> list[Type[DeclarativeBaseModel]]:
        """
        Returns the concrete models of this database: every non-abstract
        DeclarativeBaseModel subclass whose ``__db_name__`` is this
        database's name, sorted by class name. Models are found when the
        property is read, so models imported after the database is created
        are included.
        """
        models: dict[int, Type[DeclarativeBaseModel]] = {}
        pending: list[type] = list(DeclarativeBaseModel.__subclasses__())
        while pending:
            model = pending.pop()
            pending.extend(model.__subclasses__())
            if model.__dict__.get("__abstract__", False):
                continue
            if getattr(model, "__db_name__", None) == self.db_name:
                models[id(model)] = cast(Type[DeclarativeBaseModel], model)
        return sorted(models.values(), key=lambda m: (m.__name__, m.__module__))

    def request_session(self) -> AsyncSession:
        """
        This database's session of the current request, created and bound
        to the request on first use (the middleware commits or rolls it back
        and closes it when the request ends).
        """
        if not has_request_context():
            raise RuntimeError("request_session() needs an active request context.")
        ctx = get_request_context()
        if ctx.sessions is None:
            ctx.sessions = ActiveSessions()
        session = ctx.sessions.get_session(self.session_name)
        if session is None:
            session = self.create_session()
            ctx.sessions.set_session(self.session_name, session)
        return session

    @asynccontextmanager
    async def work_session(self) -> AsyncIterator[AsyncSession]:
        """
        The session for a service's own reads and writes (chat history,
        documents, ...):

        - during a request whose handler is @transactional, the request's
          session: the work is flushed at the end of the block and commits
          or rolls back together with the request (so SQLite never sees two
          writers in one request);
        - everywhere else, a session_scope() of its own, committed when the
          block exits, so no handler has to commit it.
        """
        if in_transactional_request():
            session = self.request_session()
            yield session
            await session.flush()
        else:
            async with self.session_scope() as session:
                yield session

    @asynccontextmanager
    async def session_scope(
        self, *, transactional: bool = True
    ) -> AsyncIterator[AsyncSession]:
        """
        Opens a managed session outside a request: in a scheduled job, a
        background task or a service called from one.

        The block runs in a context of its own with the session bound under
        this database's session name, so models and repositories find it
        exactly as they do during a request. Inside a request that context
        keeps the request's user, roles and request object; the request's own
        sessions are untouched. With
        ``transactional=True`` (the default) the block runs in a transaction
        that commits when it exits normally and rolls back on an exception.
        The session is always closed. The engine is connected if it is not
        connected yet, and is left connected.

        Example:
            async with db.session_scope() as session:
                await PostRepository().publish_scheduled()
        """
        if self._session_factory is None:
            await self.connect()

        with child_context(app=self.app) as ctx:
            # Work in the block commits with the block, never with a request.
            ctx.extras.pop(TRANSACTION_OPEN, None)
            try:
                async with self.create_session() as session:
                    if transactional:
                        async with session.begin():
                            with bind_session(self.session_name, session):
                                yield session
                    else:
                        with bind_session(self.session_name, session):
                            yield session
            finally:
                # Sessions of other databases opened in the block (by
                # Model.query() or a repository) belong to the block too;
                # closing them returns their connections. Their uncommitted
                # work is rolled back: use each database's own scope for it.
                await _close_sessions(ctx)


async def _close_sessions(ctx: Any) -> None:
    sessions = ctx.sessions
    if sessions is None:
        return
    for session in list(sessions.sessions.values()):
        await session.close()
    ctx.sessions = None


def in_transactional_request() -> bool:
    """
    True while a request whose handler (or its controller) is marked
    @transactional still has its commit ahead: its request sessions are
    committed when it succeeds. False once the database middleware has
    finished, for example while a streamed response body is being sent.
    """
    if not has_request_context():
        return False
    return bool(get_request_context().extras.get(TRANSACTION_OPEN, False))


def cli_session(
    db_impl_or_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Opens a managed SQL database session for a CLI command method.

    This decorator may only be applied to methods inside a CLIController
    implementation.

    The wrapped CLI method runs inside:
        - a lightweight request_context
        - an AsyncSession
        - a transaction block
        - a bind_session(...) context

    Example:
        @cli_controller
        class MyCliController(CLIController):

            @command("seed")
            @cli_session("main")
            async def seed(self) -> None:
                ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if py_inspect.isclass(func):
            raise TypeError(
                "@cli_session can only be applied to CLIController methods, "
                "not to classes."
            )

        if not py_inspect.isfunction(func) and not py_inspect.ismethod(func):
            raise TypeError(
                "@cli_session can only be applied to CLIController methods."
            )

        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            if not isinstance(self, CLIController):
                raise TypeError(
                    "@cli_session can only be used on methods of a CLIController "
                    "implementation."
                )

            db_extension: Optional["SqlDatabase[Any]"] = cast(
                Optional["SqlDatabase[Any]"],
                self.app.extensions.get(db_impl_or_name),
            )

            if db_extension is None:
                raise ValueError(
                    f"Database extension with name {db_impl_or_name!r} "
                    "is not registered."
                )

            await db_extension.connect()

            try:
                with request_context(app=self.app):
                    async with db_extension.create_session() as session:
                        async with session.begin():
                            with bind_session(db_extension.session_name, session):
                                return await run_sync_or_async(
                                    func,
                                    self,
                                    *args,
                                    **kwargs,
                                )

            finally:
                await db_extension.disconnect()

        return wrapper

    return decorator


def background_session(
    db_impl_or_name: str,
    *,
    transactional: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Opens a managed SQL database session for a method that runs outside a
    request, such as a scheduled task-manager job or a background task.

    It is the counterpart of @cli_session for a running application: the
    method runs inside ``SqlDatabase.session_scope()``, so models and
    repositories find their session as they do during a request. The engine
    stays connected afterwards, because the application owns it.

    The decorated method must belong to an object with an ``app`` attribute,
    such as an extension, a service, a task manager or a controller.

    Example:
        class Jobs(TaskManager):
            @schedule_job("interval", minutes=1)
            @background_session("main")
            async def publish_scheduled(self) -> None:
                await PostRepository().publish_due()
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if py_inspect.isclass(func):
            raise TypeError("@background_session can only be applied to methods.")

        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            app = getattr(self, "app", None)
            if app is None:
                raise TypeError(
                    "@background_session can only be used on methods of objects "
                    "with an 'app' attribute (extensions, services, task managers)."
                )

            db_extension = cast(
                Optional["SqlDatabase[Any]"],
                app.extensions.get(db_impl_or_name),
            )
            if db_extension is None:
                raise ValueError(
                    f"Database extension with name {db_impl_or_name!r} "
                    "is not registered."
                )

            async with db_extension.session_scope(transactional=transactional):
                return await run_sync_or_async(func, self, *args, **kwargs)

        return wrapper

    return decorator
