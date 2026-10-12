"""
Database sessions outside requests, the database's model list, and several
applications with their own database managers in one process.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from patera import Request, Response
from patera.controller import Controller, path, post
from patera.ctx import current_request
from patera.injectable import Inject
from patera.database.sql import (
    DeclarativeBaseModel,
    Repository,
    SqlDatabase,
    SqlDatabaseConfig,
    SqlDatabaseManager,
    background_session,
    transactional,
)

pytestmark = pytest.mark.integration


class JobsBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "jobs"


class JobNote(JobsBase):
    __tablename__ = "job_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))


class JobRun(JobsBase):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class JobsDb(SqlDatabase):
    __db_name__ = "jobs"


class JobsManager(SqlDatabaseManager):
    databases = [JobsDb]


class OtherJobsDb(SqlDatabase):
    __db_name__ = "jobs"


class OtherJobsManager(SqlDatabaseManager):
    databases = [OtherJobsDb]


class JobNoteRepository(Repository[JobNote]):
    model = JobNote


@path("/job-notes")
class JobNotes(Controller):
    notes: Inject[JobNoteRepository]

    @post("/")
    @transactional
    async def create(self, req: Request) -> Response:
        await self.notes.create_and_flush(title="from request")
        return req.res.json({"ok": True}).status(201)


def _uri(tmp_path, name: str) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / name}"


async def _create_schema(db: SqlDatabase) -> None:
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(
            JobsBase.metadata.create_all,
            tables=[JobNote.__table__, JobRun.__table__],
        )


async def _titles(db: SqlDatabase) -> list[str]:
    rows = await db.execute_raw(select(JobNote.title).order_by(JobNote.id))
    return [row["title"] for row in rows]


# ---- Several applications, each with its own manager --------------------------


async def test_each_app_uses_its_own_manager(make_app, tmp_path, client_for):
    first = make_app(
        controllers=[JobNotes],
        extensions=[JobsManager],
        JOBS_DB=SqlDatabaseConfig(DATABASE_URI=_uri(tmp_path, "first.db")),
    )
    # A second app with a differently named manager, created afterwards.
    second = make_app(
        controllers=[JobNotes],
        extensions=[OtherJobsManager],
        OTHER_JOBS_DB=SqlDatabaseConfig(DATABASE_URI=_uri(tmp_path, "second.db")),
    )
    for app, manager in ((first, JobsManager), (second, OtherJobsManager)):
        db = app.get_extension(manager).get_database("jobs")
        async with client_for(app) as client:
            await _create_schema(db)
            res = await client.post("/job-notes/")
            assert res.status_code == 201
            assert await _titles(db) == ["from request"]


def test_middleware_finds_the_manager_of_its_app(make_app, tmp_path):
    from patera.database.sql.sql_database_manager import (
        SqlDatabaseManagerMiddleware,
    )

    first = make_app(
        extensions=[JobsManager],
        JOBS_DB=SqlDatabaseConfig(DATABASE_URI=_uri(tmp_path, "a.db")),
    )
    second = make_app(
        extensions=[OtherJobsManager],
        OTHER_JOBS_DB=SqlDatabaseConfig(DATABASE_URI=_uri(tmp_path, "b.db")),
    )

    async def endpoint(req):
        return None

    assert SqlDatabaseManagerMiddleware(
        first, endpoint
    )._manager is first.get_extension(JobsManager)
    assert SqlDatabaseManagerMiddleware(
        second, endpoint
    )._manager is second.get_extension(OtherJobsManager)
    assert not hasattr(SqlDatabaseManagerMiddleware, "_sql_database_manager_name")


# ---- Model list -----------------------------------------------------------------


def test_models_list_contains_the_databases_concrete_models(make_app, tmp_path):
    app = make_app(
        extensions=[JobsManager],
        JOBS_DB=SqlDatabaseConfig(DATABASE_URI=_uri(tmp_path, "models.db")),
    )
    db = app.get_extension(JobsManager).get_database("jobs")
    models = db.models_list
    assert JobNote in models and JobRun in models
    assert JobsBase not in models
    assert all(model.__db_name__ == "jobs" for model in models)
    assert [m.__name__ for m in models] == sorted(m.__name__ for m in models)


# ---- Sessions outside requests ----------------------------------------------------


class Publisher:
    """Stands in for a task manager or service: anything with an ``app``."""

    def __init__(self, app) -> None:
        self.app = app

    @background_session("jobs")
    async def publish(self, title: str) -> int:
        note = JobNote(title=title)
        current_request.session("session").add(note)
        await current_request.session("session").flush()
        return note.id

    @background_session("jobs")
    async def fail(self) -> None:
        current_request.session("session").add(JobNote(title="rolled back"))
        await current_request.session("session").flush()
        raise RuntimeError("job failed")

    @background_session("jobs", transactional=False)
    async def count(self) -> int:
        session = current_request.session("session")
        return (await session.execute(select(func.count(JobNote.id)))).scalar_one()

    @background_session("missing")
    async def unknown_database(self) -> None:
        return None


@pytest.fixture
async def jobs_app(make_app, tmp_path):
    app = make_app(
        extensions=[JobsManager],
        JOBS_DB=SqlDatabaseConfig(DATABASE_URI=_uri(tmp_path, "jobs.db")),
    )
    db = app.get_extension(JobsManager).get_database("jobs")
    await _create_schema(db)
    yield app, db
    await db.disconnect()


async def test_background_session_commits(jobs_app):
    app, db = jobs_app
    publisher = Publisher(app)
    assert await publisher.publish("first") == 1
    assert await publisher.publish("second") == 2
    assert await _titles(db) == ["first", "second"]
    assert await publisher.count() == 2


async def test_background_session_rolls_back_on_error(jobs_app):
    app, db = jobs_app
    with pytest.raises(RuntimeError, match="job failed"):
        await Publisher(app).fail()
    assert await _titles(db) == []


async def test_background_session_connects_a_disconnected_database(jobs_app):
    app, db = jobs_app
    await db.disconnect()
    db._session_factory = None
    assert await Publisher(app).publish("after reconnect") == 1
    assert db._engine is not None  # left connected for the running app


async def test_background_session_errors(jobs_app):
    app, _ = jobs_app
    with pytest.raises(ValueError, match="'missing'"):
        await Publisher(app).unknown_database()

    class NoApp:
        @background_session("jobs")
        async def run(self) -> None:
            return None

    with pytest.raises(TypeError, match="'app' attribute"):
        await NoApp().run()


async def test_session_scope_binds_the_session(jobs_app):
    _, db = jobs_app
    async with db.session_scope() as session:
        assert current_request.session("session") is session
        session.add(JobNote(title="scoped"))
    assert await _titles(db) == ["scoped"]

    async with db.session_scope(transactional=False) as session:
        session.add(JobNote(title="not committed"))
        await session.flush()
    assert await _titles(db) == ["scoped"]


async def test_disconnect_forgets_the_session_factory(make_app, tmp_path):
    import gc
    import warnings

    app = make_app(
        extensions=[JobsManager],
        JOBS_DB=SqlDatabaseConfig(DATABASE_URI=_uri(tmp_path, "lifecycle.db")),
    )
    db = app.get_extension(JobsManager).get_database("jobs")
    await db.connect()
    await db.disconnect()
    with pytest.raises(RuntimeError, match="not connected"):
        db.create_session()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async with db.session_scope() as session:  # reconnects
            assert (await session.execute(select(1))).scalar() == 1
        await db.disconnect()  # and closes everything again
        gc.collect()
    assert db._engine is None
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]
