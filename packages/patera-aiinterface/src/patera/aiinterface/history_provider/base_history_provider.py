"""
Chat history providers.

A history provider stores the user and assistant messages of each chat
session. The system prompt is not stored: the AI service always sends the
current one first.

Providers can also keep a rolling summary of each session (used when
AiServiceConfig.HISTORY_SUMMARY is set): a short digest of the older
messages, so that only the summary and the latest messages are sent. The
messages themselves are always kept in full.
"""

from __future__ import annotations

import asyncio
import uuid
import weakref
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import ClassVar, TYPE_CHECKING, Any, Generic, Optional, Type, TypeVar, cast

from sqlalchemy import false, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from patera.database.sql import DeclarativeBaseModel, SqlDatabase

from ..service_provider.chat_response import ChatMessage

if TYPE_CHECKING:
    from ..ai_service import AiService

ModelT = TypeVar("ModelT", bound=DeclarativeBaseModel)


@dataclass(frozen=True, slots=True)
class HistorySummary:
    """A session's digest and the position of the last message it includes."""

    text: str
    covers_up_to: int


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """A message with its position in the session (0, 1, 2, ...)."""

    position: int
    message: ChatMessage


class BaseHistoryProvider(ABC):
    """
    Storage for chat sessions. Implement load() and append(); override
    new_session_id() for ids other than random UUID strings.

    For HISTORY_SUMMARY, also implement load_since(), load_summary() and
    save_summary() (SqlHistoryProvider does).
    """

    def bind(self, service: "AiService[Any, Any]") -> None:
        """Called once by the AI service that uses this provider."""

    @abstractmethod
    async def load(self, session_id: Any, limit: Optional[int]) -> list[ChatMessage]:
        """
        The session's messages, oldest first. With a limit, only the last
        ``limit`` messages.
        """

    @abstractmethod
    async def append(self, session_id: Any, messages: list[ChatMessage]) -> None:
        """Adds messages to the end of the session."""

    async def new_session_id(self) -> Any:
        """Id for a new chat session (a random UUID string by default)."""
        return str(uuid.uuid4())

    # ---- summaries (optional) ---------------------------------------------------

    @property
    def supports_summaries(self) -> bool:
        cls = type(self)
        return all(
            getattr(cls, name) is not getattr(BaseHistoryProvider, name)
            for name in ("load_since", "load_summary", "save_summary")
        )

    async def load_since(
        self, session_id: Any, after: Optional[int], limit: Optional[int]
    ) -> list[StoredMessage]:
        """
        Messages after position ``after`` (all when None), oldest first; with
        a limit, only the last ``limit`` of them.
        """
        raise NotImplementedError(f"{type(self).__name__} does not store summaries.")

    async def load_summary(self, session_id: Any) -> Optional[HistorySummary]:
        """The session's latest summary, or None."""
        raise NotImplementedError(f"{type(self).__name__} does not store summaries.")

    async def save_summary(
        self,
        session_id: Any,
        summary: HistorySummary,
        replaces: Optional[HistorySummary],
    ) -> bool:
        """
        Stores ``summary`` if the session's current summary is still
        ``replaces`` (None: the session has none yet). Returns False when
        another summary was saved in the meantime, so concurrent updates never
        overwrite each other.
        """
        raise NotImplementedError(f"{type(self).__name__} does not store summaries.")


# Databases on which _lock_in_database() locks a chat session until commit.
_LOCKING_DIALECTS = frozenset({"postgresql", "sqlite"})


class SqlHistoryProvider(BaseHistoryProvider, Generic[ModelT]):
    """
    History stored in a SQL table, one row per message:

        class ChatMessageRow(Base):
            __tablename__ = "chat_messages"
            id: Mapped[int] = mapped_column(primary_key=True)
            session_id: Mapped[str] = mapped_column(String(36), index=True)
            role: Mapped[str] = mapped_column(String(20))
            content: Mapped[str] = mapped_column(Text)
            order_number: Mapped[int] = mapped_column(Integer)

        class ChatHistory(SqlHistoryProvider[ChatMessageRow]):
            model = ChatMessageRow

    During a @transactional request, reads and writes use the request's
    session, so the messages commit (or roll back) with the request; anywhere
    else they use a short transaction of their own, so history works in plain
    requests, CLI commands and scheduled jobs without any commit by the
    caller (see SqlDatabase.work_session()).

    A session's summary is one more row in the same table, with the role
    "summary" and the order number of the last message it covers, so
    (session_id, order_number) must not be a unique key.

    Writes to one chat session never overlap, even inside @transactional
    requests whose rows commit only when the request ends. On PostgreSQL
    (an advisory lock on the chat session) and SQLite (the database's write
    lock), each write first takes a database lock that is held until its
    transaction commits, so the next writer reads the last order number only
    after that commit, in any worker process. Other databases take turns on
    an in-process lock per chat session.
    """

    model: Type[ModelT]
    SUMMARY_ROLE: ClassVar[str] = "summary"

    def __init__(
        self,
        *,
        session_id_column: str = "session_id",
        content_column: str = "content",
        role_column: str = "role",
        order_column: str = "order_number",
    ) -> None:
        self.session_id_column = session_id_column
        self.content_column = content_column
        self.role_column = role_column
        self.order_column = order_column
        self._service: Optional["AiService[Any, Any]"] = None
        self._locks: weakref.WeakValueDictionary[Any, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def bind(self, service: "AiService[Any, Any]") -> None:
        self._service = service

    def _database(self) -> SqlDatabase:
        if self._service is None:
            raise RuntimeError(
                f"{type(self).__name__} is not attached to an AI service."
            )
        database = self._service.app.extensions.get(self.model.db_name())
        if database is None:
            raise RuntimeError(
                f"No database {self.model.db_name()!r} found for {self.model.__name__}."
            )
        return cast(SqlDatabase, database)

    def _lock_for(self, session_id: Any) -> asyncio.Lock:
        """The in-process lock of a chat session (kept while anyone holds it)."""
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    @asynccontextmanager
    async def _writing(self, session_id: Any) -> AsyncIterator[AsyncSession]:
        """
        The session for one write to a chat session, with that chat session
        locked until the write commits.

        On PostgreSQL and SQLite the database lock does it, also across
        worker processes and inside @transactional requests. It is taken
        before anything else, so a writer that waits for it holds nothing
        another writer needs. Other databases take turns on the in-process
        lock, held until the work session has committed.
        """
        database = self._database()
        if make_url(database.db_uri).get_backend_name() in _LOCKING_DIALECTS:
            async with database.work_session() as session:
                await self._lock_in_database(session, session_id)
                yield session
        else:
            async with (
                self._lock_for(session_id),
                database.work_session() as session,
            ):
                yield session

    async def _lock_in_database(self, session: AsyncSession, session_id: Any) -> None:
        """
        Locks the chat session until the transaction ends, so the next writer
        reads the last order number after this one has committed.

        - PostgreSQL: a transaction-level advisory lock on this chat session.
        - SQLite: the database's write lock, taken by an UPDATE that matches
          no rows. SQLite has one writer at a time, and a transaction that
          has written keeps the lock until it commits; taking it before the
          read makes another writer wait (up to the busy timeout) instead of
          reading a number that is about to be used.
        - Other databases: nothing; the in-process lock still applies.
        """
        dialect = session.bind.dialect.name
        if dialect == "postgresql":
            key = f"{self.model.__tablename__}:{session_id}"
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": key},
            )
        elif dialect == "sqlite":
            order = self._column(self.order_column)
            await session.execute(
                update(self.model)
                .where(false())
                .values({order: order})
                .execution_options(synchronize_session=False)
            )

    def _column(self, name: str) -> Any:
        return getattr(self.model, name)

    def _in_session(self, session_id: Any) -> Any:
        return self._column(self.session_id_column) == session_id

    def _is_message(self) -> Any:
        return self._column(self.role_column) != self.SUMMARY_ROLE

    def _message(self, row: Any) -> ChatMessage:
        return ChatMessage(
            role=getattr(row, self.role_column),
            content=getattr(row, self.content_column),
        )

    async def load(self, session_id: Any, limit: Optional[int]) -> list[ChatMessage]:
        return [
            stored.message for stored in await self.load_since(session_id, None, limit)
        ]

    async def load_since(
        self, session_id: Any, after: Optional[int], limit: Optional[int]
    ) -> list[StoredMessage]:
        order = self._column(self.order_column)
        query = (
            select(self.model)
            .where(self._in_session(session_id), self._is_message())
            .order_by(order.desc())
        )
        if after is not None:
            query = query.where(order > after)
        if limit is not None:
            query = query.limit(limit)
        async with self._database().work_session() as session:
            rows = list((await session.execute(query)).scalars().all())
            return [
                StoredMessage(getattr(row, self.order_column), self._message(row))
                for row in reversed(rows)
            ]

    async def append(self, session_id: Any, messages: list[ChatMessage]) -> None:
        order = self._column(self.order_column)
        last = select(func.max(order)).where(
            self._in_session(session_id), self._is_message()
        )
        async with self._writing(session_id) as session:
            current = await session.scalar(last)
            number = -1 if current is None else int(current)
            for message in messages:
                number += 1
                row = self.model()
                setattr(row, self.session_id_column, session_id)
                setattr(row, self.role_column, message.role)
                setattr(row, self.content_column, message.content)
                setattr(row, self.order_column, number)
                session.add(row)

    def _summary_query(self, session_id: Any) -> Any:
        return (
            select(self.model)
            .where(
                self._in_session(session_id),
                self._column(self.role_column) == self.SUMMARY_ROLE,
            )
            .order_by(self._column(self.order_column).desc())
            .limit(1)
        )

    async def load_summary(self, session_id: Any) -> Optional[HistorySummary]:
        async with self._database().work_session() as session:
            row = (await session.execute(self._summary_query(session_id))).scalar()
            if row is None:
                return None
            return HistorySummary(
                text=getattr(row, self.content_column),
                covers_up_to=getattr(row, self.order_column),
            )

    async def save_summary(
        self,
        session_id: Any,
        summary: HistorySummary,
        replaces: Optional[HistorySummary],
    ) -> bool:
        async with self._writing(session_id) as session:
            row = (await session.execute(self._summary_query(session_id))).scalar()
            current = None if row is None else getattr(row, self.order_column)
            expected = None if replaces is None else replaces.covers_up_to
            if current != expected:
                return False
            if row is None:
                row = self.model()
                setattr(row, self.session_id_column, session_id)
                setattr(row, self.role_column, self.SUMMARY_ROLE)
                session.add(row)
            setattr(row, self.content_column, summary.text)
            setattr(row, self.order_column, summary.covers_up_to)
            return True
