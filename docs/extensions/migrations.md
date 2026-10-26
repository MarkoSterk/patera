# Migrations

`patera-migrate` adds SQL migrations based on [pyway](https://github.com/jasondcamp/pyway).

```sh
uv add "patera[migrate]"
```

Add the `Migrate` mixin to the database class and keep the
[database manager](database.md) registration:

```python
from patera.database.sql import SqlDatabase
from patera.migrate import Migrate


class MainDb(SqlDatabase, Migrate):
    __db_name__ = "main"
```

## Settings

Migration settings are part of the database configuration (`MAIN_DB` above). The public model
for these fields is `MigrateConfig` (`from patera.migrate import MigrateConfig`); the former
private name `_PateraPywayConfigs` remains an alias.

| Option | Default | Description |
| --- | --- | --- |
| `MIGRATE_CLI_NAME` | `"migrate"` | CLI controller name; unique per database. |
| `MIGRATE_DATABASE_MIGRATION_DIR` | `"migrations"` | Folder, relative to the application package. |
| `MIGRATE_TABLE` | `"pyway_migrations"` | Table that records applied migrations. |
| `MIGRATE_SQL_MIGRATION_PREFIX` | `"V"` | File name prefix. |
| `MIGRATE_SQL_MIGRATION_SEPARATOR` | `"__"` | Separator between version and description. |
| `MIGRATE_SQL_MIGRATION_SUFFIXES` | `".sql"` | File endings, several separated by commas. |

## Migration files

A migration is named `<prefix><version><separator><description><suffix>`, for example
`V1_0__create_notes.sql`. The version has at least two numbers (`1_0`, `2.1`, `3_0_1`).

- Files with another ending, such as a `README.md`, are ignored.
- A file with a migration ending but another name stops the command with an error, so a misnamed
  migration is never skipped silently.
- Patera does not generate migration SQL from model differences: write and review the SQL.

## Commands

```sh
uv run patera cli migrate:init       # writes app/migrations/.pyway.conf (keep it in .gitignore)
# add migrations/V01_01__create_notes.sql
uv run patera cli migrate:info
uv run patera cli migrate:migrate
uv run patera cli migrate:validate
```

`migrate:init` writes `.pyway.conf` into the migration directory. Each developer generates their
own copy, so add it to `.gitignore`. The file holds only migration settings: the connection
(including the password) is read from `DATABASE_URI` each time a command runs. A `database_*`
value set in the file overrides the URI for that developer.

Use `patera cli --list` to see the migration commands of every database.

## Good practice

- Do not rewrite applied migrations to resolve checksum mismatches; add a new migration.
- Test both a fresh database and the upgrade path.
- Apply reviewed migrations as an explicit deployment step. The CLI does not start the ASGI
  lifespan.
