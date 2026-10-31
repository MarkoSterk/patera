# SQL databases and repositories

Install `patera-database` plus the appropriate asynchronous SQLAlchemy driver.

```python
from typing import TYPE_CHECKING

from patera.database.sql import SqlDatabase, SqlDatabaseManager, SqlDatabaseConfig

if TYPE_CHECKING:
    from app import App


class NotesDb(SqlDatabase["App"]):
    __db_name__ = "notes"

class Databases(SqlDatabaseManager["App"]):
    databases = [NotesDb]
```

Register `Databases` in `app_extensions`. Declare `NOTES_DB: SqlDatabaseConfig`
on Config with `DATABASE_URI`, and a unique `DATABASE_SESSION_NAME` when using several
databases. Let the manager construct databases; independently injecting one first
can bypass manager setup. Distinguish class/config key (`NotesDb`/`NOTES_DB`),
database name (`notes`), and session name. Each database and session name must be
unique. Connection/disconnection are lifespan actions.

Models subclass `DeclarativeBaseModel` from `patera.database.sql`, with
`__tablename__`, `__db_name__`, and SQLAlchemy `Mapped` columns. Import model
modules before using metadata; declaration does not migrate a schema.
`Model.query()` uses the bound request session. Queries support filtering,
ordering, limits, pagination and terminals such as `all`/`one_or_none`.
`Repository[Model]` subclasses set `model = Model` and use a context-bound session;
repositories are shared instances, not owners of a persistent request session.

Use `@transactional` from `patera.database.sql` on writing HTTP handlers or
controllers. The middleware owns commit/rollback; successful body conversion
occurs before it commits. Non-transactional uncommitted writes roll back. Do not
manually close the request session or reuse it in background work.

Outside HTTP use `async with database.create_session() as session` and explicitly
manage transactions, or `async with database.session_scope()` for a context-bound
session that commits on success and rolls back on exceptions. Pass an explicit
session to `Model.query(session)` when not using context. `cli_session` and
`background_session` provide command/job scopes. Give each database its own scope.

Startup app hooks run before extension connection hooks; an early schema action
must explicitly connect first. `metadata.create_all` is for disposable/new schemas,
not schema evolution. Keep SQLite write transactions short; timeout settings do
not make SQLite a multi-writer database.

Sources: tutorial chapters 8 and 17; architecture chapter 16.
