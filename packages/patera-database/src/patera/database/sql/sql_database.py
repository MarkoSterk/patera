"""
sql_database.py
Module for sql database connection/integration
"""

# import asyncio
from typing import (
    Any,
    Dict,
    Optional,
    Callable,
    Tuple,
    Type,
    TypedDict,
    cast,
    TYPE_CHECKING,
    NotRequired,
)
from functools import wraps
from sqlalchemy import MetaData, Table, select, func
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

# pylint: disable-next=E0402
from patera.base_extension import BaseExtension
from .declarative_base import DeclarativeBaseModel

if TYPE_CHECKING:
    from patera import Patera


class _SqlDatabaseConfig(BaseModel):
    """Configuration options for SqlDatabase extension"""

    model_config = ConfigDict(extra="allow")

    DATABASE_URI: str = Field(description="Connection string for the database")
    DATABASE_SESSION_NAME: str = Field(
        "session",
        description=(
            "AsyncSession variable name for use "
            "with @managed_session decorator and "
            "@readonly_session decorator"
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


class SqlDatabaseConfig(TypedDict):
    DATABASE_URI: str
    DATABASE_SESSION_NAME: NotRequired[str]
    SHOW_SQL: NotRequired[bool]
    NICE_NAME: NotRequired[str]


_DIALECT_EXTRAS: Dict[str, Callable] = {
    "postgresql": _extras_postgres,
    "sqlite": _extras_sqlite,
    "mysql": _extras_mysql,
    "mariadb": _extras_mysql,
    "mssql": _extras_mssql,
    "oracle": _extras_oracle,
}


class SqlDatabase(BaseExtension):
    """
    A simple async Database interface using SQLAlchemy.
    """

    def __init__(
        self, db_name: Optional[str] = None, configs_name: str = "SQL_DATABASE"
    ) -> None:
        self._app: "Optional[Patera]" = None
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._db_uri: str = ""
        self._configs_name: str = cast(str, configs_name)
        self._configs: dict[str, str] = {}
        if db_name is None:
            db_name = configs_name.lower()
        self.__db_name__ = db_name
        self._session_name: str
        self._models: dict[str, type[DeclarativeBaseModel]] = {}
        self._number_of_tables: int = 0

    def init_app(self, app: "Patera") -> None:
        """
        Initializes the database interface
        app.get_conf("DATABASE_URI") must return a connection string like:
        "postgresql+asyncpg://user:pass@localhost/dbname"
        or "sqlite+aiosqlite:///./patera.db"
        """
        self._app = app
        self._configs = app.get_conf(self._configs_name, None)
        if self._configs is None:
            raise ValueError(
                f"Configurations for {self._configs_name} not found in app configurations."
            )
        self._configs = self.validate_configs(self._configs, _SqlDatabaseConfig)
        self._db_uri = self._configs["DATABASE_URI"]
        self._session_name = self._configs["DATABASE_SESSION_NAME"]
        self._app.add_extension(self)
        self._app.add_on_startup_method(self.connect)
        self._app.add_on_shutdown_method(self.disconnect)
        for model in self._app._db_models.get(self.__db_name__, []):
            self._models[model.__name__] = model

    async def connect(self) -> None:
        """
        Creates the async engine and session factory.
        Runs automatically when the lifespan.start signal is received
        """
        if not self._engine:
            self._engine = create_async_engine(
                cast(str, self._db_uri),
                echo=cast(bool, self._configs.get("SHOW_SQL", False)),
                pool_pre_ping=True,
                pool_recycle=1800,
            )

        self._session_factory = async_sessionmaker(
            bind=self._engine, expire_on_commit=False, autoflush=False
        )

    async def disconnect(self) -> None:
        """
        Runs automatically when the lifespan.shutdown signal is received
        """
        if self._engine:
            await self._engine.dispose()
            self._engine = None

    def create_session(self) -> AsyncSession:
        """
        Creates new session and returns session object. Used for manual session handling.

        WARNING: You must close the session manually after use with await session.close()
        or use it within an async with block.
        """
        if self._session_factory is not None:
            return cast(AsyncSession, self._session_factory())
        # pylint: disable-next=W0719
        raise Exception("Session factory is None")

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
        return self.__db_name__

    @property
    def nice_name(self) -> str:
        name: str = cast(str, self._configs.get("NICE_NAME"))
        if name is None:
            return self.db_name
        return name

    @property
    def models_list(self) -> list[Type[DeclarativeBaseModel]]:
        """List fo all models"""
        return [model for model in self._models.values()]

    @property
    def managed_session(self) -> Callable:
        """
        Returns a decorator that:
        - Creates a new AsyncSession per request.
        - Injects it into the kwargs of the request with the key "session" or custom session name.
        - Commits if no error occurs.
        - Rolls back if an unhandled error occurs.
        - Closes the session automatically afterward.
        """

        def decorator(handler: Callable) -> Callable:
            @wraps(handler)
            async def wrapper(*args, **kwargs):
                if not self._session_factory:
                    raise RuntimeError(
                        "Database is not connected. "
                        "Connection should be established automatically."
                        "Please check network connection and configurations."
                    )
                async with (
                    self._session_factory() as session
                ):  # Ensures session closure
                    async with (
                        session.begin()
                    ):  # Ensures transaction handling (auto commit/rollback)
                        kwargs[self.session_name] = session
                        return await run_sync_or_async(handler, *args, **kwargs)

            return wrapper

        return decorator

    @property
    def managed_session_for_cli(self) -> Callable:
        """
        A managed session for CLI commands which first connects to the DB
        and handles session injection and connection closing
        - Creates a new AsyncSession per request.
        - Injects it into the kwargs of the request with the key "session" or custom session name.
        - Commits if no error occurs.
        - Rolls back if an unhandled error occurs.
        - Closes the session automatically afterward.
        """

        def decorator(handler: Callable) -> Callable:
            @wraps(handler)
            async def wrapper(*args, **kwargs):
                await self.connect()  # connects to db
                assert self._session_factory is not None
                async with (
                    self._session_factory() as session
                ):  # Ensures session closure
                    async with (
                        session.begin()
                    ):  # Ensures transaction handling (auto commit/rollback)
                        kwargs[self.session_name] = session
                        result = await run_sync_or_async(handler, *args, **kwargs)
                await self.disconnect()  # disconnects from db
                return result

            return wrapper

        return decorator

    @property
    def readonly_session(self) -> Callable:
        """
        Returns a decorator that:
        - Creates a new AsyncSession per request.
        - Injects it into the kwargs of the request with the key "session" or custom session name.
        - Closes the session automatically afterward.
        - Does not commit or rollback, for read-only operations.
        """

        def decorator(handler: Callable) -> Callable:
            @wraps(handler)
            async def wrapper(*args, **kwargs):
                if not self._session_factory:
                    raise RuntimeError(
                        "Database is not connected. "
                        "Connection should be established automatically."
                        "Please check network connection and configurations."
                    )
                async with (
                    self._session_factory() as session
                ):  # Ensures session closure
                    kwargs[self.session_name] = session
                    return await run_sync_or_async(handler, *args, **kwargs)

            return wrapper

        return decorator
