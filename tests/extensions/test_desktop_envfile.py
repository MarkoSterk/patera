"""
The packaged program's settings file, desktop.env: written from the
configuration class, checked before packaging, and loaded by the program
under the environment and the installation's settings.env.
"""

from __future__ import annotations

import os
import types
from typing import Optional

import pytest

pytest.importorskip("patera.desktop")

from dotenv import dotenv_values  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from patera import BaseConfig  # noqa: E402
from patera.desktop import Desktop, DesktopConfig  # noqa: E402
from patera.desktop import desktop as desktop_module  # noqa: E402
from patera.desktop import envfile  # noqa: E402
from patera.desktop.packaging import check_env_file  # noqa: E402

pytestmark = pytest.mark.integration


class _Db(BaseModel):
    URI: str
    POOL: int = 5


class _Config(BaseConfig):
    BASE_PATH: str = "."
    APP_NAME: str = "Ledger"
    PORT: int = 8000  # set by the program: not listed
    GREETING: str = "Hello there"
    TAGS: list[str] = ["a", "b"]
    BETA: bool = True
    NICKNAME: Optional[str] = None
    DB: _Db
    DESKTOP: DesktopConfig


@pytest.fixture
def env(monkeypatch, tmp_path):
    """
    No program settings in the environment, and a temporary data folder.
    The environment is restored afterwards: load_dotenv() writes to it
    directly, past monkeypatch.
    """
    saved = dict(os.environ)
    for name in list(os.environ):
        if name.startswith("PATERA_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setattr(desktop_module.Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)
    yield monkeypatch
    os.environ.clear()
    os.environ.update(saved)


def _app(monkeypatch) -> types.SimpleNamespace:
    monkeypatch.setenv("PATERA_DB__URI", "sqlite:///dev.db")  # the development value
    configs = _Config()
    return types.SimpleNamespace(app_name=configs.APP_NAME, configs=configs)


def test_desktop_env_lists_the_applications_settings(env):
    text = envfile.env_text(_app(env))
    lines = text.splitlines()
    assert "PATERA_DB__URI=" in lines  # required: an empty line to fill in
    assert "# PATERA_DB__POOL=5" in lines
    assert '# PATERA_GREETING="Hello there"' in lines
    assert '# PATERA_TAGS=\'["a", "b"]\'' in lines
    assert "# PATERA_BETA=true" in lines
    assert "# PATERA_DESKTOP__WIDTH=1024" in lines
    # Development values are never copied, nor settings the program sets.
    assert "dev.db" not in text
    assert "PATERA_BASE_PATH" not in text and "PATERA_PORT" not in text
    # Only the application's own settings, not every built-in one.
    assert "PATERA_CORS" not in text and "PATERA_LOG_FILES" not in text


def test_the_listed_defaults_are_read_back_as_they_are(env, tmp_path):
    app = _app(env)
    uncommented = [
        line[2:] if line.startswith("# PATERA_") else line
        for line in envfile.env_text(app).splitlines()
    ]
    path = tmp_path / "all.env"
    path.write_text("\n".join(uncommented), encoding="utf-8")
    values = {name: value for name, value in dotenv_values(path).items() if value}
    values["PATERA_DB__URI"] = "sqlite:///x.db"
    for name in list(os.environ):
        if name.startswith("PATERA_"):
            env.delenv(name)
    for name, value in values.items():
        env.setenv(name, value)
    again = _Config()
    assert again.GREETING == "Hello there" and again.TAGS == ["a", "b"]
    assert again.BETA is True and again.DB.POOL == 5
    assert again.DESKTOP == DesktopConfig()


def test_desktop_env_is_not_overwritten(env, tmp_path):
    app = _app(env)
    path = envfile.write_env_file(app, tmp_path / "desktop.env")
    path.write_text("# edited\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        envfile.write_env_file(app, path)
    assert path.read_text() == "# edited\n"


def test_packaging_needs_the_required_settings(env, tmp_path, capsys):
    app = _app(env)
    # No desktop.env: the program would not start.
    with pytest.raises(RuntimeError, match="PATERA_DB__URI.*desktop:env"):
        check_env_file(app, tmp_path)
    (tmp_path / "desktop.env").write_text("PATERA_DB__URI=\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Set them in desktop.env"):
        check_env_file(app, tmp_path)

    (tmp_path / "desktop.env").write_text(
        "PATERA_DB__URI=sqlite+aiosqlite:///${PATERA_DATA_DIR}/ledger.db\n"
        "PATERA_SECRET_KEY=oops\nPATERA_MAIL__PASSWORD=hunter2\n"
        "# PATERA_API_TOKEN=commented out\n",
        encoding="utf-8",
    )
    check_env_file(app, tmp_path)
    warnings = capsys.readouterr().err
    assert "PATERA_SECRET_KEY" in warnings and "PATERA_MAIL__PASSWORD" in warnings
    assert "PATERA_API_TOKEN" not in warnings


def test_the_program_name_comes_from_the_environment_desktop_env_or_the_class(
    env, tmp_path
):
    path = tmp_path / "desktop.env"
    assert envfile.program_app_name(_Config, path) == "Ledger"
    path.write_text('PATERA_APP_NAME="Ledger Pro"\n', encoding="utf-8")
    assert envfile.program_app_name(_Config, path) == "Ledger Pro"
    env.setenv("PATERA_APP_NAME", "Ledger Test")
    assert envfile.program_app_name(_Config, path) == "Ledger Test"


def test_the_program_loads_its_settings_in_order(env, tmp_path):
    data = tmp_path / "data"
    installation = data / "settings.env"
    data.mkdir()
    bundled = tmp_path / "desktop.env"
    bundled.write_text(
        "PATERA_DB__URI=sqlite+aiosqlite:///${PATERA_DATA_DIR}/ledger.db\n"
        "PATERA_GREETING=from desktop.env\nPATERA_BETA=false\n"
        "PATERA_DESKTOP__WIDTH=1100\n",
        encoding="utf-8",
    )
    installation.write_text("PATERA_GREETING=from settings.env\n", encoding="utf-8")
    env.setenv("PATERA_BETA", "true")  # a real variable wins over both files
    envfile.load_program_env(_Config, bundled, data, installation)
    configs = _Config()
    assert configs.DB.URI == f"sqlite+aiosqlite:///{data.as_posix()}/ledger.db"
    assert configs.GREETING == "from settings.env"
    assert configs.BETA is True
    assert configs.DESKTOP.WIDTH == 1100


def test_a_secret_key_is_made_for_each_installation(env, tmp_path):
    class WithKey(_Config):
        SECRET_KEY: str = "shipped-with-the-program"

    settings = tmp_path / "settings.env"
    settings.write_text("PATERA_GREETING=hi", encoding="utf-8")  # no final newline
    envfile.ensure_secret_key(WithKey, settings)
    key = os.environ["PATERA_SECRET_KEY"]
    assert len(key) >= 40 and key != "shipped-with-the-program"
    assert dotenv_values(settings) == {
        "PATERA_GREETING": "hi",
        "PATERA_SECRET_KEY": key,
    }

    # The next start finds it in settings.env and keeps it.
    env.delenv("PATERA_SECRET_KEY")
    envfile.load_program_env(WithKey, tmp_path / "none.env", tmp_path, settings)
    envfile.ensure_secret_key(WithKey, settings)
    assert os.environ["PATERA_SECRET_KEY"] == key

    # A configuration without SECRET_KEY gets none.
    env.delenv("PATERA_SECRET_KEY")
    envfile.ensure_secret_key(_Config, tmp_path / "other.env")
    assert "PATERA_SECRET_KEY" not in os.environ
    assert not (tmp_path / "other.env").exists()


def _package_app(make_app, extra_config: str = "") -> type:
    import importlib

    from tests.extensions.test_desktop import SERVER_APP

    files = dict(SERVER_APP)
    files["server.py"] = (
        files["server.py"]
        .replace(
            "from patera.desktop import Desktop",
            "from patera.desktop import Desktop, DesktopConfig",
        )
        .replace(
            "    OPEN_API: bool = False\n",
            "    OPEN_API: bool = False\n" + extra_config,
        )
    )
    name, _ = make_app.package(files)
    return importlib.import_module(f"{name}.server").App


def test_desktop_run_shows_the_programs_settings(make_app, env, tmp_path):
    (tmp_path / "desktop.env").write_text(
        'PATERA_APP_NAME="Ledger"\nPATERA_DESKTOP__TITLE="From desktop.env"\n'
        "PATERA_DESKTOP__WIDTH=1100\n",
        encoding="utf-8",
    )
    app_class = _package_app(make_app, "    DESKTOP: DesktopConfig\n")
    desktop = app_class(cli_mode=True).get_extension(Desktop)
    env.setenv("PATERA_DESKTOP__WIDTH", "1300")  # as if from the development .env
    desktop.load_program_env()
    assert desktop._window_configs is not None
    assert desktop._window_configs.TITLE == "From desktop.env"
    assert desktop._window_configs.WIDTH == 1300  # .env wins over desktop.env
    assert desktop._window_app_name == "Ledger"
    data = desktop_module.user_data_dir("Ledger")
    assert os.environ["PATERA_DATA_DIR"] == data.as_posix()


def test_run_in_window_loads_desktop_env(make_app, env, tmp_path):
    app_class = _package_app(make_app)
    (tmp_path / "desktop.env").write_text(
        "PATERA_THEME=dark\nPATERA_CACHE_DIR=${PATERA_DATA_DIR}/cache\n",
        encoding="utf-8",
    )
    seen: dict[str, Optional[str]] = {}

    def window(app, url, *, dev_tools, **kwargs):
        seen.update(
            theme=os.environ.get("PATERA_THEME"),
            cache=os.environ.get("PATERA_CACHE_DIR"),
        )

    env.setattr(desktop_module, "show_window", window)
    desktop_module.run_in_window(app_class)
    data = desktop_module.user_data_dir("Patera app")
    assert seen == {"theme": "dark", "cache": f"{data.as_posix()}/cache"}
