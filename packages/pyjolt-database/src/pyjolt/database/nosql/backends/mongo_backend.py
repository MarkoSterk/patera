"""
MongoDB backend
"""

from typing import Optional, Callable, Any, Iterable, Mapping, TYPE_CHECKING, cast

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:
    raise

from .async_nosql_backend_protocol import AsyncNoSqlBackendBase

if TYPE_CHECKING:
    from pyjolt import PyJolt


class MongoBackend(AsyncNoSqlBackendBase):
    def __init__(self, uri: str, database: Optional[str] = None) -> None:
        self._client: Optional[Any] = None
        self._db: Optional[Any] = None
        self._uri: str = uri
        self._database: Optional[str] = database

    @classmethod
    def configure_from_app(
        cls, app: "PyJolt", configs: dict[str, Any]
    ) -> "AsyncNoSqlBackendBase":
        uri = cast(str, configs.get("DATABASE_URI"))
        database = cast(str, configs.get("DATABASE"))
        return cls(uri, database)

    async def connect(self) -> None:
        # Connect client
        self._client = AsyncIOMotorClient(self._uri)
        # Choose DB (or leave None; database_handle() will return client)
        self._db = self._client[self._database] if self._database else None

        # quick ping to verify connectivity
        try:
            await self._client.admin.command("ping")
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Failed to connect to MongoDB at {self._uri}: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    def database_handle(self) -> Any:
        # Prefer a db handle if configured; otherwise, return client
        return self._db if self._db is not None else self._client

    def supports_transactions(self) -> bool:
        # Mongo supports transactions on replica sets / sharded clusters with WiredTiger.
        return True

    async def start_session(self) -> Any:
        if not self._client:
            raise RuntimeError("Mongo client not connected.")
        return await self._client.start_session()

    async def with_transaction(
        self, fn: Callable[..., Any], *args, session: Any = None, **kwargs
    ) -> Any:
        # If session provided, run a transaction; else just call directly.
        if session is None:
            return await fn(*args, **kwargs)

        async def runner(sess):
            return await fn(*args, session=sess, **kwargs)

        # Motor session has method 'with_transaction'
        return await session.with_transaction(runner)

    # ---- Collection / CRUD ----

    def get_collection(self, name: str) -> Any:
        db_or_client = self.database_handle()
        if hasattr(db_or_client, "__getitem__"):  # db['collection']
            return db_or_client[name]
        # If only client exists but no db name given:
        raise RuntimeError(
            "No database selected. Set NOSQL_DATABASE or use database['<db>'][collection]."
        )

    async def find_one(
        self,
        collection: str,
        filter: Mapping[str, Any],
        *,
        session: Any = None,
        **kwargs,
    ) -> Any:
        coll = self.get_collection(collection)
        return await coll.find_one(filter, session=session, **kwargs)

    async def find_many(
        self,
        collection: str,
        filter: Mapping[str, Any] | None = None,
        *,
        session: Any = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None,
        sort: Optional[Iterable[tuple[str, int]]] = None,
        **kwargs,
    ) -> list[Any]:
        filter = filter or {}
        coll = self.get_collection(collection)
        cursor = coll.find(filter, session=session, **kwargs)
        if sort:
            cursor = cursor.sort(list(sort))
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit or 0)

    async def insert_one(
        self, collection: str, doc: Mapping[str, Any], *, session: Any = None, **kwargs
    ) -> Any:
        coll = self.get_collection(collection)
        return await coll.insert_one(doc, session=session, **kwargs)

    async def insert_many(
        self,
        collection: str,
        docs: Iterable[Mapping[str, Any]],
        *,
        session: Any = None,
        **kwargs,
    ) -> Any:
        coll = self.get_collection(collection)
        return await coll.insert_many(list(docs), session=session, **kwargs)

    async def update_one(
        self,
        collection: str,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        *,
        upsert: bool = False,
        session: Any = None,
        **kwargs,
    ) -> Any:
        coll = self.get_collection(collection)
        return await coll.update_one(
            filter, update, upsert=upsert, session=session, **kwargs
        )

    async def delete_one(
        self,
        collection: str,
        filter: Mapping[str, Any],
        *,
        session: Any = None,
        **kwargs,
    ) -> Any:
        coll = self.get_collection(collection)
        return await coll.delete_one(filter, session=session, **kwargs)

    async def aggregate(
        self,
        collection: str,
        pipeline: Iterable[Mapping[str, Any]],
        *,
        session: Any = None,
        **kwargs,
    ) -> list[Any]:
        coll = self.get_collection(collection)
        cursor = coll.aggregate(list(pipeline), session=session, **kwargs)
        return await cursor.to_list(length=None)

    async def execute_raw(self, *args, **kwargs) -> Any:
        """
        For MongoDB, you can call arbitrary db.command(...) via:
            await db.execute_raw("command", {"ping": 1})
        Or pass a callable to run with the database handle.
        """
        db = self.database_handle()
        if callable(args[0]):
            fn = args[0]
            return await fn(db, *args[1:], **kwargs)

        # Simple command passthrough:
        if isinstance(args[0], str):
            cmd = args[0]
            arg = args[1] if len(args) > 1 else {}
            return await db.command(
                {cmd: arg} if not isinstance(arg, Mapping) else {cmd: 1, **arg}
            )

        raise TypeError("Unsupported execute_raw usage for MongoBackend.")
