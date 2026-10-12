from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from patera import Request, Response
from patera.cli import CLIController, cli_controller, command
from patera.controller import Controller, get, path, post
from patera.ctx import current_request
from patera.database.sql import (
    DeclarativeBaseModel,
    Repository,
    SqlDatabase,
    SqlDatabaseConfig,
    SqlDatabaseManager,
    cli_session,
    query,
    transactional,
)
from patera.injectable import Inject

pytestmark = pytest.mark.integration


class Base(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "main"


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))


class MainDb(SqlDatabase):
    __db_name__ = "main"


class Databases(SqlDatabaseManager):
    databases = [MainDb]


class NoteRepository(Repository[Note]):
    model = Note

    @query("SELECT * FROM notes WHERE title LIKE :pattern ORDER BY id")
    async def search(self, pattern: str) -> list[Note]: ...

    @query("SELECT COUNT(*) AS n FROM notes")
    async def total(self) -> int: ...

    @query("SELECT * FROM notes WHERE id = :note_id")
    async def find(self, note_id: int) -> Optional[Note]: ...

    @query("SELECT id, title FROM notes ORDER BY id")
    async def rows(self) -> list[dict]: ...

    @query("UPDATE notes SET title = :title WHERE id = :note_id")
    async def rename(self, note_id: int, title: str) -> None: ...

    @query("DELETE FROM notes WHERE title LIKE :pattern")
    async def delete_matching(self, pattern: str) -> int: ...

    @query("DELETE FROM notes WHERE id = :note_id")
    async def delete_unannotated(self, note_id: int): ...

    @query("UPDATE notes SET title = title")
    async def touch_rows(self) -> list[dict]: ...


@path("/notes")
class NoteController(Controller):
    notes: Inject[NoteRepository]

    @get("/")
    async def index(self, req: Request) -> Response:
        items = await self.notes.list_all()
        return req.res.json([{"id": n.id, "title": n.title} for n in items])

    @post("/")
    @transactional
    async def create(self, req: Request) -> Response:
        data = await req.json()
        note = await self.notes.create_and_flush(title=data["title"])
        if data.get("fail"):
            raise RuntimeError("rollback please")
        return req.res.json({"id": note.id}).status(201)

    @post("/no-commit")
    async def create_without_transaction(self, req: Request) -> Response:
        await self.notes.create_and_flush(title="discarded")
        return req.res.json({"ok": True})

    @get("/query")
    async def via_model_query(self, req: Request) -> Response:
        page = await Note.query().order_by(Note.id).paginate(page=1, per_page=2)
        first = await Note.query().filter_by(title="b").first()
        return req.res.json(
            {
                "total": page.total,
                "pages": page.pages,
                "has_next": page.has_next,
                "items": [n.title for n in page.items],
                "first_b": first.id if first else None,
                "count": await Note.query().count(),
                "exists": await Note.query().filter(Note.title == "zzz").exists(),
                "sorted": [
                    n.title
                    for n in await Note.query().order_by_strings("title DESC").all()
                ],
            }
        )

    @get("/custom")
    async def custom(self, req: Request) -> Response:
        found = await self.notes.find(1)
        missing = await self.notes.find(999)
        return req.res.json(
            {
                "search": [n.title for n in await self.notes.search("%a%")],
                "total": await self.notes.total(),
                "found": found.title if found else None,
                "missing": missing,
                "rows": await self.notes.rows(),
                "session_is_shared": current_request.session("session")
                is self.notes.session,
            }
        )

    @post("/dml")
    @transactional
    async def dml(self, req: Request) -> Response:
        renamed = await self.notes.rename(1, "renamed")
        deleted = await self.notes.delete_matching("b%")
        unannotated = await self.notes.delete_unannotated(999)
        try:
            await self.notes.touch_rows()
            error = None
        except TypeError as exc:
            error = str(exc)
        return req.res.json(
            {
                "renamed": renamed,
                "deleted": deleted,
                "unannotated": unannotated,
                "error": error,
            }
        )


@pytest.fixture
async def app(make_app, tmp_path, client_for):
    application = make_app(
        controllers=[NoteController],
        extensions=[Databases],
        DEBUG=False,
        MAIN_DB=SqlDatabaseConfig(
            DATABASE_URI=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
        ),
    )
    return application


async def _create_schema(app):
    db = app.get_extension(Databases).get_database("main")
    await db.connect()
    async with db.engine.begin() as conn:
        # Only this module's table: all models share one metadata object.
        await conn.run_sync(Base.metadata.create_all, tables=[Note.__table__])


async def test_transactional_requests(app, client_for):
    async with client_for(app) as client:
        await _create_schema(app)
        res = await client.post("/notes/", json={"title": "a"})
        assert res.status_code == 201
        await client.post("/notes/", json={"title": "b"})

        # failure inside a transactional handler rolls back
        res = await client.post("/notes/", json={"title": "c", "fail": True})
        assert res.status_code == 500

        # non transactional requests never commit
        await client.post("/notes/no-commit")

        res = await client.get("/notes/")
        assert [n["title"] for n in res.json()] == ["a", "b"]


async def test_queries_and_repository(app, client_for):
    async with client_for(app) as client:
        await _create_schema(app)
        for title in ("a", "b", "ab"):
            await client.post("/notes/", json={"title": title})

        data = (await client.get("/notes/query")).json()
        assert data == {
            "total": 3,
            "pages": 2,
            "has_next": True,
            "items": ["a", "b"],
            "first_b": 2,
            "count": 3,
            "exists": False,
            "sorted": ["b", "ab", "a"],
        }

        data = (await client.get("/notes/custom")).json()
        assert data["search"] == ["a", "ab"]
        assert data["total"] == 3
        assert data["found"] == "a"
        assert data["missing"] is None
        assert data["rows"][0] == {"id": 1, "title": "a"}
        assert data["session_is_shared"] is True


async def test_query_methods_run_dml_statements(app, client_for):
    async with client_for(app) as client:
        await _create_schema(app)
        for title in ("a", "b1", "b2", "c"):
            await client.post("/notes/", json={"title": title})

        data = (await client.post("/notes/dml")).json()
        assert data["renamed"] is None
        assert data["deleted"] == 2
        assert data["unannotated"] == 0
        assert "-> None, or -> int" in data["error"]

        res = await client.get("/notes/")
        assert [n["title"] for n in res.json()] == ["renamed", "c"]


async def test_order_by_strings_rejects_unknown_columns(app, client_for):
    async with client_for(app):
        await _create_schema(app)
        db = app.get_extension(Databases).get_database("main")
        async with db.create_session() as session:
            with pytest.raises(ValueError):
                Note.query(session).order_by_strings("password")
            with pytest.raises(ValueError):
                Note.query(session).order_by_strings("title sideways")


def test_manager_lookup_and_names(make_app, tmp_path):
    app = make_app(
        extensions=[Databases],
        MAIN_DB={"DATABASE_URI": f"sqlite+aiosqlite:///{tmp_path / 'x.db'}"},
    )
    manager = app.get_extension(Databases)
    db = manager["main"]
    assert manager.get_default_database() is db
    assert db.db_name == "main"
    assert db.nice_name == "main"
    assert app.extensions["main"] is db
    with pytest.raises(KeyError):
        manager.get_database("other")


def test_duplicate_session_names_are_rejected(make_app, tmp_path):
    class SecondDb(SqlDatabase):
        __db_name__ = "second"

    class TwoDatabases(SqlDatabaseManager):
        databases = [MainDb, SecondDb]

    uri = f"sqlite+aiosqlite:///{tmp_path / 'y.db'}"
    with pytest.raises(RuntimeError, match="DATABASE_SESSION_NAME"):
        make_app(
            extensions=[TwoDatabases],
            MAIN_DB=SqlDatabaseConfig(DATABASE_URI=uri),
            SECOND_DB=SqlDatabaseConfig(DATABASE_URI=uri),
        )

    app = make_app(
        extensions=[TwoDatabases],
        MAIN_DB=SqlDatabaseConfig(DATABASE_URI=uri),
        SECOND_DB=SqlDatabaseConfig(
            DATABASE_URI=uri, DATABASE_SESSION_NAME="second_session"
        ),
    )
    assert len(app.get_extension(TwoDatabases).databases_list) == 2


def test_db_name_defaults_to_class_name(make_app, tmp_path):
    class AnalyticsDb(SqlDatabase):
        pass

    app = make_app(ANALYTICS_DB=SqlDatabaseConfig(DATABASE_URI="sqlite+aiosqlite://"))
    assert AnalyticsDb(app).db_name == "analyticsdb"


@cli_controller(name="seed")
class SeedCLI(CLIController):
    @command("run")
    @cli_session("main")
    async def run(self, title: str) -> int:
        note = Note(title=title)
        current_request.session("session").add(note)
        await current_request.session("session").flush()
        return note.id


async def test_cli_session(make_app, tmp_path):
    uri = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    app = make_app(
        cli_mode=True,
        extensions=[Databases],
        MAIN_DB=SqlDatabaseConfig(DATABASE_URI=uri),
    )
    await _create_schema(app)
    await app.get_extension(Databases).get_database("main").disconnect()
    cli = SeedCLI(app)
    assert await cli.run("from cli") == 1

    db = app.get_extension(Databases).get_database("main")
    await db.connect()
    rows = await db.execute_raw(select(Note.title))
    assert [r["title"] for r in rows] == ["from cli"]
    assert await db.count_tables() == 1
    per_table, total = await db.count_rows_exact()
    assert per_table == {"notes": 1} and total == 1
    overview = await db.collect_db_overview()
    assert overview
    await db.disconnect()
