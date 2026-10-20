import sqlite3
import sys
from pathlib import Path

import pytest

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
SECRET = "test-secret-key-that-is-long-enough-for-hs256-signing"
PASSWORD = "long-password-123"


def _forget_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


@pytest.fixture
def database(tmp_path) -> Path:
    return tmp_path / "exams.sqlite3"


@pytest.fixture(scope="session", autouse=True)
def example_package():
    """Imports this example's ``app`` package once (models register once)."""
    sys.path.insert(0, str(EXAMPLE_ROOT))
    _forget_app_modules()
    yield
    _forget_app_modules()
    sys.path.remove(str(EXAMPLE_ROOT))


@pytest.fixture
def env(monkeypatch, tmp_path, database):
    monkeypatch.setenv("PATERA_SECRET_KEY", SECRET)
    monkeypatch.setenv(
        "PATERA_EXAMS_DB__DATABASE_URI", f"sqlite+aiosqlite:///{database.as_posix()}"
    )
    monkeypatch.setenv("PATERA_LOG_FILES__PATH", str(tmp_path / "app.jsonl"))
    monkeypatch.setenv("PATERA_STARTUP_BANNER", "false")


@pytest.fixture
def cli_app(env):
    from app import App

    application = App(cli_mode=True)
    yield application
    application._remove_logger_sinks()


@pytest.fixture
def create_user(cli_app, monkeypatch):
    from app.cli import users_cli

    def create(email: str, role: str = "instructor", password: str = PASSWORD) -> None:
        monkeypatch.setattr(users_cli, "getpass", lambda _prompt: password)
        cli_app.run_cli("users:create", command_args=[email, role])

    return create


@pytest.fixture
def exams_app(cli_app, create_user):
    cli_app.run_cli("migrate:migrate")
    cli_app.run_cli("migrate:validate")
    create_user("teacher@example.com", "both")
    create_user("other@example.com", "instructor")

    from app import App

    application = App()
    yield application
    application._remove_logger_sinks()


@pytest.fixture
def db(database):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()
