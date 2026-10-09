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


def test_create_and_read_pyway_config(migrate, monkeypatch):
    app, mig = migrate
    assert mig._migrations_path.is_dir()
    mig.create_pyway_config()
    text = mig._configs_path.read_text()
    assert "database_type: postgresql" in text
    assert "database_port: 5433" in text

    # A blank line, a comment and a value containing ": " are tolerated.
    mig._configs_path.write_text(text + "\n# comment\ndatabase_password: a: b\n")
    captured = {}

    class FakeConfigFile:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    from patera.migrate import migrate as migrate_module

    monkeypatch.setattr(migrate_module, "PywayConfigFile", FakeConfigFile)
    ctrl = app._cli_controllers["migrate"]
    ctrl._get_configs_from_file()
    ctrl._clear_env_vars()
    assert captured["database_password"] == "a: b"
    assert captured["database_type"] == "postgresql"
