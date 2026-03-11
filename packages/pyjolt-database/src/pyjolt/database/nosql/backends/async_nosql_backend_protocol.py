"""
Protocls for async NoSQL backends.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Any, Iterable, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from pyjolt import PyJolt


class AsyncNoSqlBackendBase(ABC):
    """
    Minimal async adapter interface a backend must implement.
    """

    @classmethod
    @abstractmethod
    def configure_from_app(
        cls, app: "PyJolt", configs: dict[str, Any]
    ) -> "AsyncNoSqlBackendBase":
        """
        Classmethod to configure backend from app config.
        Called during NoSqlDatabase.init_app().
        """
        ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def database_handle(self) -> Any:
        """
        Returns an object representing the 'database' to use inside handlers.
        For backends without a database concept, return a client/root handle.
        """
        ...

    @abstractmethod
    def supports_transactions(self) -> bool: ...

    @abstractmethod
    async def start_session(self) -> Any:
        """
        Return a session/context object usable in transactions (or None if unsupported).
        """
        ...

    @abstractmethod
    async def with_transaction(
        self, fn: Callable[..., Any], *args, session: Any = None, **kwargs
    ) -> Any:
        """
        Execute fn inside a transaction if supported; otherwise call fn directly.
        """
        ...

    @abstractmethod
    def get_collection(self, name: str) -> Any: ...

    @abstractmethod
    async def find_one(
        self,
        collection: str,
        filter: Mapping[str, Any],
        *,
        session: Any = None,
        **kwargs,
    ) -> Any: ...

    @abstractmethod
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
    ) -> list[Any]: ...

    @abstractmethod
    async def insert_one(
        self, collection: str, doc: Mapping[str, Any], *, session: Any = None, **kwargs
    ) -> Any: ...

    @abstractmethod
    async def insert_many(
        self,
        collection: str,
        docs: Iterable[Mapping[str, Any]],
        *,
        session: Any = None,
        **kwargs,
    ) -> Any: ...

    @abstractmethod
    async def update_one(
        self,
        collection: str,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        *,
        upsert: bool = False,
        session: Any = None,
        **kwargs,
    ) -> Any: ...

    @abstractmethod
    async def delete_one(
        self,
        collection: str,
        filter: Mapping[str, Any],
        *,
        session: Any = None,
        **kwargs,
    ) -> Any: ...

    @abstractmethod
    async def aggregate(
        self,
        collection: str,
        pipeline: Iterable[Mapping[str, Any]],
        *,
        session: Any = None,
        **kwargs,
    ) -> list[Any]: ...

    @abstractmethod
    async def execute_raw(self, *args, **kwargs) -> Any:
        """
        Backend escape hatch for commands that don't fit the generic surface.
        For MongoDB, this could be db.command(...), collection.bulk_write(...), etc.
        """
        ...
