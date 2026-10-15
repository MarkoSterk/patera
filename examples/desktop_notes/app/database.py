from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from patera.database.sql import (
    DeclarativeBaseModel,
    Repository,
    SqlDatabase,
    SqlDatabaseManager,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotesDb(SqlDatabase):
    """
    The notes database. It creates its tables when the application starts:
    a desktop program has no setup command for its users to run.

    create_all() only adds missing tables. Once the program has users, a
    change to an existing table needs a migration (patera-migrate).
    """

    __db_name__ = "notes"

    def init(self) -> None:
        super().init()  # registers connect() as a startup action
        # Runs after connect(): startup actions run in the order they are added.
        self.app.add_on_startup_method(self.create_tables)

    async def create_tables(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)


class Databases(SqlDatabaseManager):
    databases = [NotesDb]


class Base(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "notes"


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class NoteRepository(Repository[Note]):
    model = Note
