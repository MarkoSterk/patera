# SQL migrations

Install `patera-migrate`. Use its mixin on a managed database:

```python
from patera.database.sql import SqlDatabase
from patera.migrate import Migrate

class NotesDb(SqlDatabase, Migrate):
    __db_name__ = "notes"
```

Keep the database manager registration. The mixin supplies Pyway integration and
CLI commands. Configure `MIGRATE_CLI_NAME` (default `migrate`) and
`MIGRATE_DATABASE_MIGRATION_DIR` (default `migrations`, relative to application
root) on the database settings. Multiple databases need unique CLI aliases.

Write reviewed SQL files, e.g. `V1__create_notes.sql`. Defaults are prefix `V`,
separator `__`, suffix `.sql`. Patera does not generate migration SQL from model
diffs. Use `patera cli --list` to inspect the installed migration commands, then
run the appropriate info/validate/migrate command against the intended database.
Do not rewrite applied migrations to resolve checksum mismatches; add a new
migration and test both a fresh database and an upgrade path.

Directory creation occurs during construction. Make migration resources available
in deployments and keep schema changes an explicit operational step. The CLI
uses its own resource boundary; it does not start ASGI lifespan automatically.

Sources: tutorial chapter 9; architecture chapter 16.
