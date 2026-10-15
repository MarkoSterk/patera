from __future__ import annotations

import os
import sys
from typing import Any, Optional

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


class PagingCLI(CLIController):
    @command("page")
    def page(self, number: Optional[int] = None, size: int | None = None) -> Any:
        return number, size


def test_optional_arguments_are_converted(make_app):
    ctrl = PagingCLI(make_app(cli_mode=True))
    assert ctrl.prepare_cli_args(ctrl.page, ["3", "20"]) == [3, 20]
    assert ctrl.prepare_cli_args(ctrl.page, []) == [None, None]


def test_run_command(cli_app):
    ctrl = cli_app._cli_controllers["tools"]
    assert ctrl.run_command(ctrl.add, command_args=["3", "4"]) == 7


def test_failing_command_exits_non_zero(cli_app, capsys):
    ctrl = cli_app._cli_controllers["tools"]
    with pytest.raises(SystemExit) as exc:
        ctrl.run_command(ctrl.fail, command_args=[])
    assert exc.value.code == 1
    assert "nope" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command_name", "message"),
    [
        ("bad-format", "Invalid command name"),
        (None, "Invalid command name"),
        ("unknown:add", "was not found"),
        ("tools:missing", "not found"),
    ],
)
def test_run_cli_dispatch_failures_exit_non_zero(
    cli_app, capsys, command_name, message
):
    with pytest.raises(SystemExit) as exc:
        cli_app.run_cli(command_name)
    assert exc.value.code == 1
    assert message in capsys.readouterr().err


def test_run_cli_dispatch_success(cli_app):
    assert cli_app.run_cli("tools:add", command_args=["3", "4"]) is None


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


def test_prod_explains_how_to_install_granian(tmp_path, monkeypatch):
    import sys

    from patera.cli.start_project import _start_prod

    # None in sys.modules makes "import granian" fail as if it were missing.
    monkeypatch.setitem(sys.modules, "granian", None)
    with pytest.raises(RuntimeError, match=r"patera\[prod\]"):
        _start_prod(str(tmp_path), app="app:App")


def test_prod_loads_only_an_explicit_env_file(tmp_path, monkeypatch):
    import os

    import granian

    from patera.cli.start_project import _start_prod

    served = []

    class FakeGranian:
        def __init__(self, target, **kwargs):
            served.append((target, kwargs))

        def serve(self):
            pass

    monkeypatch.setattr(granian, "Granian", FakeGranian)
    # setenv + delenv registers the variables so monkeypatch removes them again
    # after the test (values loaded from the env file must not leak).
    for name in ("PATERA_TEST_PROD_VALUE", "PATERA_PORT", "PATERA_HOST"):
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)
    monkeypatch.setenv("PATERA_DEBUG", "1")
    (tmp_path / ".env.dev").write_text("PATERA_TEST_PROD_VALUE=dev\n")
    (tmp_path / ".env.prod").write_text(
        "PATERA_TEST_PROD_VALUE=prod\nPATERA_PORT=8123\n"
    )
    monkeypatch.delenv("PATERA_PORT", raising=False)

    _start_prod(str(tmp_path), app="app:App")
    assert "PATERA_TEST_PROD_VALUE" not in os.environ  # .env.dev is not searched
    assert os.environ["PATERA_DEBUG"] == "0"
    assert served[-1][1]["address"] == "0.0.0.0"
    assert served[-1][1]["port"] == 80

    # Each CLI run is a separate process: forget the address written back above.
    monkeypatch.delenv("PATERA_PORT")
    monkeypatch.delenv("PATERA_HOST")
    _start_prod(str(tmp_path), app="app:App", env_file=".env.prod")
    assert os.environ["PATERA_TEST_PROD_VALUE"] == "prod"
    assert served[-1][0] == "app:App"
    assert served[-1][1]["port"] == 8123
    assert os.environ["PATERA_PORT"] == "8123"


def _address_app(monkeypatch, tmp_path, name, body):
    """Writes a module defining an application class with the given config body."""
    import sys

    module = tmp_path / f"{name}.py"
    module.write_text(
        "from patera import Patera, app\n"
        "from patera.configuration_base import BaseConfig\n\n"
        "class Cfg(BaseConfig):\n"
        f"{body}"
        "\n@app(__name__, configs=Cfg)\n"
        "class App(Patera):\n"
        "    pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, name, raising=False)
    return f"{name}:App"


@pytest.fixture
def clean_address_env(monkeypatch):
    for name in ("PATERA_HOST", "PATERA_PORT"):
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)


@pytest.mark.usefixtures("clean_address_env")
@pytest.mark.parametrize(
    "production, expected", [(False, ("localhost", 3000)), (True, ("0.0.0.0", 80))]
)
def test_server_address_command_defaults(tmp_path, monkeypatch, production, expected):
    import os

    from patera.cli.start_project import resolve_server_address

    target = _address_app(
        monkeypatch, tmp_path, f"addr_default_{production}", "    pass\n"
    )
    assert resolve_server_address(target, production=production) == expected
    assert os.environ["PATERA_HOST"] == expected[0]
    assert os.environ["PATERA_PORT"] == str(expected[1])


@pytest.mark.usefixtures("clean_address_env")
def test_server_address_uses_config_class_defaults(tmp_path, monkeypatch):
    from patera.cli.start_project import resolve_server_address

    target = _address_app(
        monkeypatch,
        tmp_path,
        "addr_class",
        '    HOST: str = "127.0.0.2"\n    PORT: int = 9001\n',
    )
    assert resolve_server_address(target, production=False) == ("127.0.0.2", 9001)


@pytest.mark.usefixtures("clean_address_env")
def test_server_address_environment_wins_and_prod_maps_localhost(tmp_path, monkeypatch):
    from patera.cli.start_project import resolve_server_address

    target = _address_app(monkeypatch, tmp_path, "addr_env", "    PORT: int = 9001\n")
    monkeypatch.setenv("PATERA_HOST", "localhost")
    monkeypatch.setenv("PATERA_PORT", "7000")
    assert resolve_server_address(target, production=False) == ("localhost", 7000)
    assert resolve_server_address(target, production=True) == ("0.0.0.0", 7000)


@pytest.mark.usefixtures("clean_address_env")
def test_server_address_falls_back_when_the_app_cannot_be_imported():
    from patera.cli.start_project import resolve_server_address

    assert resolve_server_address("no_such_module:App", production=False) == (
        "localhost",
        3000,
    )


def test_start_cli_without_an_app_exits_non_zero(tmp_path, monkeypatch, capsys):
    from patera.cli import start_project

    monkeypatch.delenv("PATERA_IMPORT", raising=False)
    monkeypatch.setattr(start_project, "find_patera_app_import", lambda *a: None)
    with pytest.raises(SystemExit) as exc:
        start_project.start_cli(str(tmp_path), "cli", command_name="tools:add")
    assert exc.value.code == 1
    assert "Failed to locate Patera implementation" in capsys.readouterr().err


@pytest.mark.parametrize("starter", ["start_dev", "start_prod"])
def test_server_start_failures_exit_non_zero(tmp_path, monkeypatch, capsys, starter):
    from patera.cli import start_project

    def broken(*args, **kwargs):
        raise RuntimeError("port in use")

    monkeypatch.setattr(start_project, f"_{starter}", broken)
    with pytest.raises(SystemExit) as exc:
        getattr(start_project, starter)(str(tmp_path), starter)
    assert exc.value.code == 1
    assert "port in use" in capsys.readouterr().err


def test_missing_dev_server_dependency_exits_non_zero(tmp_path, monkeypatch, capsys):
    from patera.cli import start_project

    def missing(*args, **kwargs):
        raise ImportError("No module named 'uvicorn'")

    monkeypatch.setattr(start_project, "_start_dev", missing)
    with pytest.raises(SystemExit) as exc:
        start_project.start_dev(str(tmp_path), "dev")
    assert exc.value.code == 1
    assert "Install patera[dev]" in capsys.readouterr().err


def test_start_testing_returns_the_pytest_exit_code(tmp_path, monkeypatch):
    from patera.cli import start_project

    monkeypatch.setattr(pytest, "main", lambda args: 3)
    assert start_project.start_testing(str(tmp_path), "test", env_file=None) == 3


@pytest.mark.parametrize(
    ("argv", "env_file", "pytest_args"),
    [
        ([], None, []),
        (["-k", "login", "-q"], None, ["-k", "login", "-q"]),
        (["-q", "--env-file", ".env.ci", "tests"], ".env.ci", ["-q", "tests"]),
        (["--env-file=.env.ci", "-x"], ".env.ci", ["-x"]),
        (["--", "-q", "--env-file", "x"], None, ["-q", "--env-file", "x"]),
    ],
)
def test_patera_test_passes_options_in_any_order(
    monkeypatch, argv, env_file, pytest_args
):
    from patera.cli import cli as cli_module

    captured = {}
    monkeypatch.setitem(
        cli_module.methods, "test", lambda cwd, **kwargs: captured.update(kwargs) or 0
    )
    monkeypatch.setattr(sys, "argv", ["patera", "test", *argv])
    assert cli_module.main() == 0
    assert captured == {
        "command": "test",
        "env_file": env_file,
        "pytest_args": pytest_args,
    }


def test_patera_test_loads_env_test_only_when_present(tmp_path, monkeypatch):
    from patera.cli import start_project

    seen = []
    monkeypatch.setattr(pytest, "main", lambda args: seen.append(args) or 0)
    monkeypatch.delenv("PATERA_FROM_TEST_ENV", raising=False)
    # No .env.test: tests still run.
    assert start_project.start_testing(str(tmp_path), "test") == 0
    (tmp_path / ".env.test").write_text("PATERA_FROM_TEST_ENV=yes\n")
    assert start_project.start_testing(str(tmp_path), "test", pytest_args=["-q"]) == 0
    assert os.environ.pop("PATERA_FROM_TEST_ENV") == "yes"
    assert seen == [[], ["-q"]]


def test_patera_test_with_a_missing_env_file_exits_cleanly(tmp_path, capsys):
    from patera.cli import start_project

    with pytest.raises(SystemExit) as exc:
        start_project.start_testing(str(tmp_path), "test", env_file=".env.missing")
    assert exc.value.code == 1
    assert "Environment file not found" in capsys.readouterr().err


@cli_controller(name="db")
class DbCLI(CLIController):
    @command("seed", help="Load example data")
    async def seed(self, count: int, verbose: bool = False) -> None:
        return None


def test_cli_commands_lists_names_usage_and_help(cli_app):
    cli_app.register_cli_controller(DbCLI(cli_app))
    commands = cli_app.cli_commands()
    names = [c.name for c in commands]
    assert names == ["db:seed", "tools:add", "tools:fail", "tools:flag"]
    by_name = {c.name: c for c in commands}
    assert by_name["tools:add"].usage == "<a:int> [b:int=2]"
    assert by_name["tools:add"].help == "Add two numbers"
    assert by_name["db:seed"].usage == "<count:int> [verbose:bool=False]"
    assert by_name["tools:fail"].usage == ""


def test_print_cli_commands(cli_app, capsys):
    cli_app.print_cli_commands()
    out = capsys.readouterr().out
    assert out.startswith("Available commands:\n")
    assert "tools:add <a:int> [b:int=2]" in out
    assert "Add two numbers" in out


def test_print_cli_commands_without_commands(make_app, capsys):
    make_app(cli_mode=True).print_cli_commands()
    assert "No CLI commands are registered." in capsys.readouterr().out


@pytest.mark.parametrize("extra", [{}, {"list": True, "command_name": "tools:add"}])
def test_start_cli_without_a_command_lists_commands(
    tmp_path, monkeypatch, capsys, cli_app, extra
):
    from patera.cli import start_project

    monkeypatch.setattr(start_project, "_resolve_app_path", lambda *a: "x:App")
    monkeypatch.setattr(
        start_project, "import_module", lambda path: lambda **kw: cli_app
    )
    start_project.start_cli(str(tmp_path), "cli", **extra)
    assert "tools:add" in capsys.readouterr().out


def test_cli_controller_names_must_be_unique(cli_app):
    @cli_controller(name="tools")
    class OtherTools(CLIController):
        @command("other")
        async def other(self) -> None:
            return None

    with pytest.raises(ValueError, match="'tools' is used by both"):
        cli_app.register_cli_controller(OtherTools(cli_app))
    # Registering the same instance again is harmless.
    existing = cli_app._cli_controllers["tools"]
    cli_app.register_cli_controller(existing)


def test_auto_discovery_names_modules_that_failed_to_import(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setenv("PATERA_APP_PACKAGE", "broken_app")
    monkeypatch.delenv("PATERA_IMPORT", raising=False)
    (tmp_path / "broken_app").mkdir()
    (tmp_path / "broken_app" / "__init__.py").write_text(
        "import a_module_that_does_not_exist\n"
    )
    from patera import Patera

    with pytest.raises(SystemExit) as exc:
        from patera.cli.start_project import _resolve_app_path

        _resolve_app_path(None, tmp_path, Patera)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "ModuleNotFoundError" in err  # the real error is shown
    assert "'broken_app' failed to import" in err
    assert "Failed to locate Patera implementation" not in err
