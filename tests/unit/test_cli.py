from __future__ import annotations

import sys

import pytest

from patera.cli import CLIController, cli_controller, command
from patera.cli.start_project import (
    find_patera_app_import,
    load_env_file,
    path_to_module,
)


@cli_controller(name="tools")
class ToolsCLI(CLIController):
    @command("add", help="Add two numbers")
    async def add(self, a: int, b: int = 2) -> int:
        return a + b

    @command("flag")
    def flag(self, value: bool, ratio: float) -> tuple[bool, float]:
        return value, ratio

    @command("fail")
    async def fail(self) -> None:
        raise RuntimeError("nope")


@pytest.fixture
def cli_app(make_app):
    app = make_app(cli_mode=True)
    app.register_cli_controller(ToolsCLI(app))
    return app


def test_cli_controller_registration(cli_app):
    ctrl = cli_app._cli_controllers["tools"]
    assert ctrl.find_method("add") is not None
    assert ctrl.find_method("missing") is None


def test_prepare_cli_args_with_string_annotations(cli_app):
    ctrl = cli_app._cli_controllers["tools"]
    assert ctrl.prepare_cli_args(ctrl.add, ["3"]) == [3, 2]
    assert ctrl.prepare_cli_args(ctrl.flag, ["yes", "0.5"]) == [True, 0.5]
    with pytest.raises(ValueError):
        ctrl.prepare_cli_args(ctrl.add, [])
    with pytest.raises(ValueError):
        ctrl.prepare_cli_args(ctrl.add, ["1", "2", "3"])
    with pytest.raises(ValueError):
        ctrl.convert_value("maybe", bool)


def test_run_command(cli_app):
    ctrl = cli_app._cli_controllers["tools"]
    assert ctrl.run_command(ctrl.add, command_args=["3", "4"]) == 7


def test_failing_command_exits_non_zero(cli_app, capsys):
    ctrl = cli_app._cli_controllers["tools"]
    with pytest.raises(SystemExit) as exc:
        ctrl.run_command(ctrl.fail, command_args=[])
    assert exc.value.code == 1
    assert "nope" in capsys.readouterr().err


def test_run_cli_dispatch(cli_app, capsys):
    cli_app.run_cli("bad-format")
    assert "Invalid command name" in capsys.readouterr().out
    cli_app.run_cli("unknown:add")
    assert "was not found" in capsys.readouterr().out
    cli_app.run_cli("tools:missing")
    assert "not found" in capsys.readouterr().out


def test_cli_controllers_not_registered_in_http_mode(make_app):
    app = make_app()
    app.register_cli_controller(ToolsCLI(app))
    assert app._cli_controllers == {}


def test_path_to_module(tmp_path):
    assert path_to_module(tmp_path / "app" / "__init__.py", tmp_path) == "app"
    assert path_to_module(tmp_path / "app" / "main.py", tmp_path) == "app.main"


def test_load_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("PATERA_TEST_ENV_VALUE", raising=False)
    (tmp_path / ".env.custom").write_text("PATERA_TEST_ENV_VALUE=42\n")
    loaded = load_env_file(str(tmp_path), ".env.custom")
    assert loaded == tmp_path / ".env.custom"
    import os

    assert os.environ["PATERA_TEST_ENV_VALUE"] == "42"
    with pytest.raises(RuntimeError):
        load_env_file(str(tmp_path), ".env.missing")
    assert load_env_file(str(tmp_path / "empty_dir_that_has_no_env")) is None


def test_find_patera_app_import(tmp_path, monkeypatch):
    pkg = tmp_path / "proj" / "myapp"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "import os\n"
        "from patera import Patera, BaseConfig, app\n"
        "class Config(BaseConfig):\n"
        "    BASE_PATH: str = os.path.dirname(__file__)\n"
        "class NotAnApp(Patera):\n"
        "    pass\n"
        "@app(__name__, configs=Config)\n"
        "class MyApp(Patera[Config]):\n"
        "    pass\n"
    )
    monkeypatch.setenv("PATERA_APP_PACKAGE", "myapp")
    monkeypatch.syspath_prepend(str(tmp_path / "proj"))
    try:
        assert (
            find_patera_app_import(__import__("patera").Patera, tmp_path / "proj")
            == "myapp:MyApp"
        )
    finally:
        sys.modules.pop("myapp", None)


def test_main_parses_cli_arguments(monkeypatch):
    from patera.cli import cli as cli_module

    captured = {}

    def fake_start_cli(cwd, **kwargs):
        captured.update(kwargs)

    monkeypatch.setitem(cli_module.methods, "cli", fake_start_cli)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "patera",
            "cli",
            "--app",
            "app:App",
            "--env-file",
            ".env.x",
            "db:migrate",
            "a",
            "b",
        ],
    )
    cli_module.main()
    assert captured["app"] == "app:App"
    assert captured["env_file"] == ".env.x"
    assert captured["command_name"] == "db:migrate"
    assert captured["command_args"] == ["a", "b"]
