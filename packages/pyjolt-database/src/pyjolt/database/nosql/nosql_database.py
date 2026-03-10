"""
NoSQL Database Module
"""

from pydantic import BaseModel, Field
from typing import (
    Optional,
    Callable,
    Any,
    Iterable,
    Mapping,
    TYPE_CHECKING,
    TypedDict,
    cast,
    Type,
    NotRequired,
)
from functools import wraps

from .backends.async_nosql_backend_protocol import AsyncNoSqlBackendBase
from ...base_extension import BaseExtension
from ...utilities import run_sync_or_async


if TYPE_CHECKING:
    from ...pyjolt import PyJolt


class _NoSqlDatabaseConfig(BaseModel):
    """Configuration options for NoSqlDatabase extension."""

    BACKEND: Type[AsyncNoSqlBackendBase] = Field(
        description="Backend class implementing AsyncNoSqlBackendBase."
    )
    DATABASE_URI: str = Field(description="Connection string for the NoSQL backend.")
    DATABASE_NAME: Optional[str] = Field(
        default=None, description="Database / keyspace name (if backend uses it)."
    )
    DB_INJECT_NAME: Optional[str] = Field(
        default="db", description="Kwarg name injected by decorators (database handle)."
    )
    SESSION_NAME: Optional[str] = Field(
        default="session",
        description="Kwarg name injected by @managed_database (session/transaction handle).",
    )


class NoSqlDatabaseConfig(TypedDict):
    BACKEND: Type[AsyncNoSqlBackendBase]
    DATABASE_URI: str
    DATABASE_NAME: NotRequired[str]
    INJECT_NAME: NotRequired[str]
    SESSION_NAME: NotRequired[str]


class NoSqlDatabase(BaseExtension):
    """
    A simple async NoSQL Database interface with pluggable backends.
    """

    def __init__(
        self, db_name: str = "nosql", configs_name: str = "NOSQL_DATABASE"
    ) -> None:
        self._app: Optional["PyJolt"] = None
        self._configs_name = configs_name
        self._configs: dict[str, Any] = {}
        self.__db_name__ = db_name

        # Effective config
        self.backend_name: Optional[str] = None
        self.uri: Optional[str] = None
        self.database: Optional[str] = None
        self.inject_name: str = "db"
        self.session_name: str = "session"

        # Backend instance
        self._backend: AsyncNoSqlBackendBase = cast(AsyncNoSqlBackendBase, None)

    # ---- App lifecycle ----

    def init_app(self, app: "PyJolt") -> None:
        """
        Initializes the NoSQL interface.
        Required config keys (with optional variable_prefix):
            - BACKEND
            - DATABASE_URI
        Optional:
            - DATABASE
            - INJECT_NAME (default "db")
            - SESSION_NAME (default "session")
        """
        self._app = app
        self._configs = app.get_conf(self._configs_name, None)
        if self._configs is None:
            raise ValueError(f"Missing {self._configs_name} configuration.")
        self._configs = self.validate_configs(self._configs, _NoSqlDatabaseConfig)

        self.backend_cls = self._configs.get("BACKEND")
        self.uri = self._configs.get("DATABASE_URI")
        self.database = self._configs.get("DATABASE_NAME")
        self.inject_name = cast(str, self._configs.get("INJECT_NAME"))
        self.session_name = cast(str, self._configs.get("SESSION_NAME"))

        if not self.backend_cls or not self.uri:
            raise RuntimeError(
                "Missing NOSQL_BACKEND or NOSQL_DATABASE_URI configuration."
            )
        if not issubclass(self.backend_cls, AsyncNoSqlBackendBase):
            raise RuntimeError(
                "NOSQL_BACKEND must be a subclass of AsyncNoSqlBackendBase."
            )

        self._backend = cast(
            AsyncNoSqlBackendBase, self.backend_cls
        ).configure_from_app(app, self._configs)

        app.add_extension(self)
        app.add_on_startup_method(self.connect)
        app.add_on_shutdown_method(self.disconnect)

    async def connect(self) -> None:
        """
        Creates the backend client/connection. Runs on lifespan.start
        """
        if not self._backend:
            raise RuntimeError("Backend not initialized. Call init_app() first.")
        await self._backend.connect()

    async def disconnect(self) -> None:
        """
        Disposes backend resources. Runs on lifespan.shutdown
        """
        if self._backend:
            await self._backend.disconnect()

    @property
    def db_name(self) -> str:
        return self.__db_name__

    @property
    def backend(self) -> AsyncNoSqlBackendBase:
        if not self._backend:
            raise RuntimeError("Backend not connected. Was init_app/connect called?")
        return self._backend

    def database_handle(self) -> Any:
        return self.backend.database_handle()

    def get_collection(self, name: str) -> Any:
        return self.backend.get_collection(name)

    async def find_one(
        self, collection: str, filter: Mapping[str, Any], **kwargs
    ) -> Any:
        return await self.backend.find_one(collection, filter, **kwargs)

    async def find_many(
        self, collection: str, filter: Mapping[str, Any] | None = None, **kwargs
    ) -> list[Any]:
        return await self.backend.find_many(collection, filter, **kwargs)

    async def insert_one(
        self, collection: str, doc: Mapping[str, Any], **kwargs
    ) -> Any:
        return await self.backend.insert_one(collection, doc, **kwargs)

    async def insert_many(
        self, collection: str, docs: Iterable[Mapping[str, Any]], **kwargs
    ) -> Any:
        return await self.backend.insert_many(collection, docs, **kwargs)

    async def update_one(
        self,
        collection: str,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        **kwargs,
    ) -> Any:
        return await self.backend.update_one(collection, filter, update, **kwargs)

    async def delete_one(
        self, collection: str, filter: Mapping[str, Any], **kwargs
    ) -> Any:
        return await self.backend.delete_one(collection, filter, **kwargs)

    async def aggregate(
        self, collection: str, pipeline: Iterable[Mapping[str, Any]], **kwargs
    ) -> list[Any]:
        return await self.backend.aggregate(collection, pipeline, **kwargs)

    async def execute_raw(self, *args, **kwargs) -> Any:
        """
        Escape hatch for backend-specific commands. See MongoBackend.execute_raw docstring.
        """
        return await self.backend.execute_raw(*args, **kwargs)

    @property
    def managed_database(self) -> Callable:
        """
        Decorator that:
        - Injects a database/client handle into handler kwargs under NOSQL_INJECT_NAME ("db" by default).
        - If the backend supports transactions, opens a session+transaction for the duration
          and commits/aborts automatically on exit.
        """

        def decorator(handler: Callable) -> Callable:
            @wraps(handler)
            async def wrapper(*args, **kwargs):
                backend = self.backend
                inject_key = self.inject_name
                handle = backend.database_handle()

                # default injection
                kwargs[inject_key] = handle

                if not backend.supports_transactions():
                    # No transaction semantics; just run.
                    return await run_sync_or_async(handler, *args, **kwargs)

                # Transaction-capable flow
                session = await backend.start_session()

                async def _call_with_session(*_args, **_kwargs):
                    # Some backends (Mongo) accept 'session' in calls; handlers can pass it through.
                    _kwargs.setdefault(self.session_name, session)
                    return await run_sync_or_async(handler, *_args, **_kwargs)

                try:
                    return await backend.with_transaction(
                        _call_with_session, *args, **kwargs, session=session
                    )
                finally:
                    # session ended in with_transaction, but just in case
                    try:
                        await session.end_session()  # type: ignore[attr-defined]
                    except Exception:
                        pass

            return wrapper

        return decorator
