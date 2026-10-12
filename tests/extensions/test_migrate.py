from __future__ import annotations

import pytest

from patera.database.sql import SqlDatabase, SqlDatabaseConfig
from patera.migrate import Migrate


class MigratedDb(SqlDatabase, Migrate):
    __db_name__ = "main"


@pytest.fixture
def migrate(make_app, tmp_path):
    app = make_app(
        cli_mode=True,
        MIGRATED_DB=SqlDatabaseConfig(
            DATABASE_URI="postgresql+asyncpg://user:p%40ss@db.example:5433/app",
            MIGRATE_DATABASE_MIGRATION_DIR="db/migrations",
        ),
    )
    db = MigratedDb(app)
    return app, db._migrate


def test_cli_controller_registered(migrate):
    app, _ = migrate
    assert "migrate" in app._cli_controllers


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("sqlite+aiosqlite:///./app.db", {"type": "sqlite", "database": "./app.db"}),
        (
            "sqlite:////var/data/app.db",
            {"type": "sqlite", "database": "/var/data/app.db"},
        ),
        (
            "postgresql+asyncpg://user:pw@host:5432/name",
            {
                "type": "postgresql",
                "username": "user",
                "password": "pw",
                "host": "host",
                "port": "5432",
                "database": "name",
            },
        ),
    ],
)
def test_parse_database_uri(migrate, uri, expected):
    _, mig = migrate
    parsed = mig.parse_database_uri(uri)
    for key, value in expected.items():
        assert parsed[key] == value


def _captured_settings(app, monkeypatch) -> dict:
    captured: dict = {}

    class FakeConfigFile:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    from patera.migrate import migrate as migrate_module

    monkeypatch.setattr(migrate_module, "PywayConfigFile", FakeConfigFile)
    ctrl = app._cli_controllers["migrate"]
    ctrl._get_configs_from_file()
    ctrl._clear_env_vars()
    return captured


def test_pyway_config_file_holds_no_credentials(migrate):
    _, mig = migrate
    assert mig._migrations_path.is_dir()
    mig.create_pyway_config()
    text = mig._configs_path.read_text()
    assert "database_migration_dir: db/migrations" in text
    assert "database_table: pyway_migrations" in text
    for secret in (
        "p@ss",
        "p%40ss",
        "database_username",
        "db.example",
        "database_password",
    ):
        assert secret not in text


def test_connection_comes_from_the_database_uri(migrate, monkeypatch):
    app, mig = migrate
    mig.create_pyway_config()
    captured = _captured_settings(app, monkeypatch)
    assert captured["database_type"] == "postgresql"
    assert captured["database_username"] == "user"
    assert captured["database_password"] == "p@ss"  # decoded
    assert captured["database_host"] == "db.example"
    assert captured["database_port"] == "5433"
    assert captured["database_name"] == "app"


def test_config_file_values_override_and_are_optional(migrate, monkeypatch):
    app, mig = migrate
    # Without a config file the commands still have everything they need.
    assert _captured_settings(app, monkeypatch)["database_name"] == "app"

    mig.create_pyway_config()
    text = mig._configs_path.read_text()
    # A blank line, a comment and a value containing ": " are tolerated.
    mig._configs_path.write_text(
        text + "\n# comment\ndatabase_host: replica: 1\ndatabase_table: history\n"
    )
    captured = _captured_settings(app, monkeypatch)
    assert captured["database_host"] == "replica: 1"
    assert captured["database_table"] == "history"
    assert captured["database_password"] == "p@ss"


def test_percent_encoded_credentials_are_decoded(migrate):
    _, mig = migrate
    parsed = mig.parse_database_uri(
        "postgresql+asyncpg://us%3Aer:p%40ss%2Fw%25rd@host:5432/my%20db"
    )
    assert parsed["username"] == "us:er"
    assert parsed["password"] == "p@ss/w%rd"
    assert parsed["database"] == "my db"


class ReportsDb(SqlDatabase, Migrate):
    __db_name__ = "reports"


def test_two_migrating_databases_keep_their_own_names(make_app):
    app = make_app(
        cli_mode=True,
        MIGRATED_DB=SqlDatabaseConfig(
            DATABASE_URI="sqlite+aiosqlite:///./main.db",
            MIGRATE_CLI_NAME="migrate-main",
        ),
        REPORTS_DB=SqlDatabaseConfig(
            DATABASE_URI="sqlite+aiosqlite:///./reports.db",
            MIGRATE_CLI_NAME="migrate-reports",
            MIGRATE_DATABASE_MIGRATION_DIR="reports_migrations",
        ),
    )
    main = MigratedDb(app)._migrate
    reports = ReportsDb(app)._migrate
    controllers = app._cli_controllers
    assert controllers["migrate-main"] is main._cli_controller
    assert controllers["migrate-reports"] is reports._cli_controller
    # The names stay attached to their own controllers.
    assert main._cli_controller.ctrl_name == "migrate-main"
    assert reports._cli_controller.ctrl_name == "migrate-reports"
    assert main._cli_controller._ext is main
    assert reports._cli_controller._ext is reports
    names = [c.name for c in app.cli_commands()]
    assert "migrate-main:migrate" in names and "migrate-reports:migrate" in names


def test_two_databases_with_the_same_migration_name_conflict(make_app):
    app = make_app(
        cli_mode=True,
        MIGRATED_DB=SqlDatabaseConfig(DATABASE_URI="sqlite+aiosqlite:///./main.db"),
        REPORTS_DB=SqlDatabaseConfig(
            DATABASE_URI="sqlite+aiosqlite:///./reports.db",
            MIGRATE_DATABASE_MIGRATION_DIR="reports_migrations",
        ),
    )
    MigratedDb(app)
    with pytest.raises(ValueError, match="Set a different MIGRATE_CLI_NAME"):
        ReportsDb(app)


def _sqlite_app(make_app, tmp_path, **settings):
    database = tmp_path / "app.db"
    app = make_app(
        cli_mode=True,
        MIGRATED_DB=SqlDatabaseConfig(
            DATABASE_URI=f"sqlite+aiosqlite:///{database}", **settings
        ),
    )
    db = MigratedDb(app)
    return db._migrate, database


def _tables(database) -> set[str]:
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(database)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {name for (name,) in rows}


async def test_migrations_run_with_the_default_names(make_app, tmp_path, capsys):
    mig, database = _sqlite_app(make_app, tmp_path)
    (mig._migrations_path / "V1_0__notes.sql").write_text(
        "CREATE TABLE notes (id INTEGER PRIMARY KEY);"
    )
    (mig._migrations_path / "README.md").write_text("Not a migration.")
    await mig._cli_controller.migrate()
    assert "notes" in _tables(database)
    assert "V1_0__notes.sql SUCCESS" in capsys.readouterr().out


async def test_migration_naming_settings(make_app, tmp_path, capsys):
    mig, database = _sqlite_app(
        make_app,
        tmp_path,
        MIGRATE_SQL_MIGRATION_PREFIX="R",
        MIGRATE_SQL_MIGRATION_SEPARATOR="--",
        MIGRATE_SQL_MIGRATION_SUFFIXES=".up.sql, .ddl",
    )
    (mig._migrations_path / "R1_0--notes.up.sql").write_text(
        "CREATE TABLE notes (id INTEGER PRIMARY KEY);"
    )
    (mig._migrations_path / "R1_1--tags.ddl").write_text(
        "CREATE TABLE tags (id INTEGER PRIMARY KEY);"
    )
    (mig._migrations_path / "notes.txt").write_text("ignored")
    await mig._cli_controller.migrate()
    assert {"notes", "tags"} <= _tables(database)
    output = capsys.readouterr().out
    assert "R1_0--notes.up.sql SUCCESS" in output
    assert "R1_1--tags.ddl SUCCESS" in output

    # A file with a migration ending but another naming is an error,
    # never silently skipped.
    (mig._migrations_path / "R1_2__wrong.up.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError, match="does not match the configured naming"):
        await mig._cli_controller.migrate()


async def test_pyway_names_are_restored_after_a_command(make_app, tmp_path):
    from pyway import settings
    from pyway.helpers import Utils

    mig, _ = _sqlite_app(make_app, tmp_path, MIGRATE_SQL_MIGRATION_PREFIX="R")
    original = Utils.__dict__["get_version_from_name"]
    await mig._cli_controller.info()
    assert settings.SQL_MIGRATION_PREFIX == "V"
    assert Utils.__dict__["get_version_from_name"] is original
    assert Utils.get_version_from_name("V2_1__x.sql") == "2.1"
