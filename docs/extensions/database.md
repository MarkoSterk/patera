# SQL databases

`patera-database` integrates async [SQLAlchemy](https://www.sqlalchemy.org): databases, request
sessions, repositories and transactions.

```sh
uv add "patera[database]"
```

Install a driver for your database too: `aiosqlite` is included; use for example `asyncpg` for
PostgreSQL.

## Setup

```python
# app/database.py
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from patera.database.sql import DeclarativeBaseModel, SqlDatabase, SqlDatabaseManager


class MainDb(SqlDatabase):
    __db_name__ = "main"


class Databases(SqlDatabaseManager):
    databases = [MainDb]


class Base(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "main"          # models are bound to a database by name


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
```

```python
# app/configs.py
from patera.database.sql import SqlDatabaseConfig

class Config(BaseConfig):
    ...
    MAIN_DB: SqlDatabaseConfig = SqlDatabaseConfig(DATABASE_URI="sqlite+aiosqlite:///./app.db")
```

```python
# app/__init__.py
@app(__name__, configs=Config)
class App(Patera[Config]):
    app_extensions = [Databases]
```

The engine connects on startup and is disposed on shutdown. Register **only the manager**, not
the individual databases; injecting a database independently first can bypass the manager setup.

Distinguish the class and its config key (`MainDb` / `MAIN_DB`), the database name (`main`) and
the session name. With several databases, give each one a unique `__db_name__` **and** a unique
`DATABASE_SESSION_NAME`.

!!! note "Schemas"

    Declaring models does not create or migrate tables. Use [migrations](migrations.md) for
    schema evolution; `metadata.create_all` is only for disposable or brand-new schemas.

## Settings

`SqlDatabaseConfig`:

| Option | Default | Description |
| --- | --- | --- |
| `DATABASE_URI` | required | SQLAlchemy async URL. |
| `DATABASE_SESSION_NAME` | `"session"` | Name of the request session; unique per database. |
| `SHOW_SQL` | `False` | Log every executed SQL statement. |
| `NICE_NAME` | `None` | Display name in the admin dashboard; defaults to the database name. |
| `EXPIRE_ON_COMMIT` | `False` | Expire session objects on commit. |
| `AUTOFLUSH` | `False` | Autoflush the session. |
| `SQLITE_FOREIGN_KEYS` | `False` | SQLite only: run `PRAGMA foreign_keys=ON` on every connection so `FOREIGN KEY` constraints (such as `ON DELETE CASCADE`) are enforced. |
| `SQLITE_BUSY_TIMEOUT` | `None` | SQLite only: seconds a connection waits for another connection's lock before failing with "database is locked". `None` keeps the driver's default of 5 seconds, or a `?timeout=` in `DATABASE_URI`. |

```sh
PATERA_MAIN_DB__DATABASE_URI=postgresql+asyncpg://user:pass@db/app
PATERA_MAIN_DB__SQLITE_FOREIGN_KEYS=true
```

## Sessions and transactions

During a request, model queries and repositories share **one session per database**. At the end
of the request, the manager middleware commits it if the controller or endpoint is marked
`@transactional` and no exception occurred; otherwise all changes are rolled back.

```python
from patera.database.sql import Repository, query, transactional
from patera.injectable import Inject


class NoteRepository(Repository[Note]):
    model = Note

    @query("SELECT * FROM notes WHERE title LIKE :pattern ORDER BY id")
    async def search(self, pattern: str) -> list[Note]: ...   # SQL with bound parameters


@path("/notes")
class NoteApi(Controller[App]):
    notes: Inject[NoteRepository]

    @get("/")
    async def index(self, req: Request) -> Response:
        page = await Note.query().order_by(Note.id).paginate(page=1, per_page=20)
        return req.res.json({"total": page.total, "titles": [n.title for n in page.items]})

    @post("/")
    @transactional
    async def create(self, req: Request) -> Response:
        note = await self.notes.create_and_flush(title=(await req.json())["title"])
        return req.res.json({"id": note.id}).status(201)
```

- Successful body conversion happens before the commit. A failure after the commit (for example
  while streaming) cannot undo it.
- Do not close the request session manually or reuse it in background work.

## Queries

`Model.query()` returns a chainable `AsyncQuery`:

- builders: `where` / `filter`, `filter_by`, `join`, `order_by`, `order_by_strings("title DESC")`,
  `limit`, `offset`,
- terminal methods: `all`, `first`, `one`, `one_or_none`, `count`, `exists`, `paginate`.

## Repositories

`Repository[Model]` subclasses set `model = Model` and offer `get`, `get_one_by`, `first_by`,
`list_all`, `list_by`, `count`, `exists`, `create`, `create_and_flush`, `add`, `add_all`, `save`,
`delete`, `flush`, `refresh`, `paginate` and `execute`.

`@query` methods run SQL with bound parameters and map rows to models, Pydantic or dataclass
types, dicts or scalars based on the return annotation (`Optional[...]` allows no result).

Repositories are shared singletons; they use the context-bound session and do not own a session.

## Outside requests

Outside HTTP requests, open sessions explicitly:

```python
async with db.create_session() as session:
    notes = await Note.query(session).all()
```

| Tool | Use |
| --- | --- |
| `db.create_session()` | a plain session; manage transactions yourself |
| `async with db.session_scope()` | a context-bound session that commits on success and rolls back on exceptions |
| `@cli_session("main")` | opens a session and a transaction for a [CLI command](../guide/cli.md) |
| `@background_session("main")` | a managed session for a scheduled job (place it below `@schedule_job`) |

Give each database its own scope.

## The manager

`SqlDatabaseManager` gives access to the databases: `manager.get_database("main")`,
`manager["main"]`, `manager.get_default_database()`.

## Notes

- Application startup hooks run before the extension's connection hooks; a schema action in an
  early hook must connect explicitly first.
- Keep SQLite write transactions short; timeout settings do not make SQLite a multi-writer
  database.
- Socket handlers: see [WebSockets](../guide/websockets.md#security-and-resources).
