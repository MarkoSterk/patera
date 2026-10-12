from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from patera.aiinterface.augmentation_provider.embeddings import VectorColumn
from patera.database.sql import DeclarativeBaseModel, SqlDatabase, SqlDatabaseManager


class ChatDb(SqlDatabase):
    __db_name__ = "chat"


class Databases(SqlDatabaseManager):
    databases = [ChatDb]


class Base(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "chat"


class ChatMessageRow(Base):
    """One message of a chat session (the history)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    order_number: Mapped[int] = mapped_column(Integer)


class Document(Base):
    """A text the assistant can look up (the augmentation documents)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    vector = mapped_column(VectorColumn(384))  # the embedding model's dimension
