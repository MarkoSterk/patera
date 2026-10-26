"""
The Desktop extension: ``patera cli desktop:run`` starts the application in
a separate process, shows it in a window and stops it when the window closes.
"""

from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("patera.desktop")

from patera.desktop import Desktop, DesktopConfig  # noqa: E402
from patera.desktop import desktop as desktop_module  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch, tmp_path):
    """
    The user's data folder is a temporary one, on every platform. The
    environment is restored afterwards: the program's settings files are
    loaded into it directly, past monkeypatch.
    """
    saved = dict(os.environ)
    for name in ("PATERA_DATA_DIR", "PATERA_SECRET_KEY"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setattr(desktop_module.Path, "home", lambda: tmp_path / "home")
    yield
    os.environ.clear()
    os.environ.update(saved)


def _desktop(make_app, **config: Any) -> Desktop:
    app = make_app(extensions=[Desktop], cli_mode=True, **config)
    return app.get_extension(Desktop)


def test_the_run_command_is_registered(make_app):
    desktop = _desktop(make_app)
    commands = {command.name: command for command in desktop.app.cli_commands()}
    assert commands["desktop:run"].usage == "[mode:str='dev']"
    assert (
        commands["desktop:package"].usage
        == "[output:str='dist/desktop'] [spec:str='desktop.spec']"
    )
    assert commands["desktop:spec"].usage == "[path:str='desktop.spec']"


def test_the_window_opens_the_index_page(make_app):
    assert _desktop(make_app).index_url(3000) == "http://127.0.0.1:3000/"
    assert (
        _desktop(make_app, URL_PREFIX="/demo").index_url(4000)
        == "http://127.0.0.1:4000/demo/"
    )
    assert (
        _desktop(make_app, DESKTOP=DesktopConfig(INDEX_PAGE="/dashboard")).index_url(5)
        == "http://127.0.0.1:5/dashboard"
    )
    absolute = DesktopConfig(INDEX_PAGE="https://example.com/start")
    assert _desktop(make_app, DESKTOP=absolute).index_url(5) == absolute.INDEX_PAGE


def test_the_server_runs_the_cli_with_the_application(make_app):
    desktop = _desktop(make_app)
    app_class = type(desktop.app)
    assert desktop.server_command("prod") == [
        sys.executable,
        "-m",
        "patera.cli",
        "prod",
        "--app",
        f"{app_class.__module__}:{app_class.__qualname__}",
    ]


class _Steps:
    """Records what run() does, in order, instead of doing it."""

    def __init__(self, desktop: Desktop, fail_at: str = "") -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail_at = fail_at
        desktop.start_server = self.start_server  # type: ignore[method-assign]
        desktop.wait_until_ready = self.wait_until_ready  # type: ignore[method-assign]
        desktop.show_window = self.show_window  # type: ignore[method-assign]
        desktop.stop_server = self.stop_server  # type: ignore[method-assign]

    def _step(self, name: str, value: Any) -> None:
        self.calls.append((name, value))
        if name == self.fail_at:
            raise RuntimeError(name)

    def start_server(self, mode, port):
        self._step("start", (mode, port))
        return "server"

    def wait_until_ready(self, server, port):
        self._step("ready", port)

    def show_window(self, url, dev_tools=False):
        # GUI toolkits only work on the main thread.
        assert threading.current_thread() is threading.main_thread()
        self._step("window", (url, dev_tools))

    def stop_server(self, server):
        self._step("stop", server)


def test_run_starts_the_server_shows_the_window_and_stops_the_server(make_app):
    desktop = _desktop(make_app, PORT=4321)
    steps = _Steps(desktop)
    desktop.app.run_cli("desktop:run", command_args=["prod"])
    assert steps.calls == [
        ("start", ("prod", 4321)),
        ("ready", 4321),
        ("window", ("http://127.0.0.1:4321/", False)),
        ("stop", "server"),
    ]


@pytest.mark.parametrize("fail_at", ["ready", "window"])
def test_the_server_is_stopped_when_something_fails(make_app, fail_at):
    desktop = _desktop(make_app)
    steps = _Steps(desktop, fail_at=fail_at)
    with pytest.raises(RuntimeError):
        desktop.run()
    assert steps.calls[-1] == ("stop", "server")


def test_an_unknown_mode_is_refused(make_app):
    with pytest.raises(ValueError, match="'dev' or 'prod'"):
        _desktop(make_app).run("staging")


SERVER_APP = {
    "server.py": """
from patera import BaseConfig, Patera, app
from patera.desktop import Desktop


class Config(BaseConfig):
    BASE_PATH: str = __file__
    STARTUP_BANNER: bool = False
    OPEN_API: bool = False


@app(__name__, configs=Config)
class App(Patera):
    app_extensions = [Desktop]
""",
    "api/__init__.py": "",
    "api/home_api.py": """
from patera import Request, Response
from patera.controller import Controller, get, path


@path("/")
class Home(Controller):
    @get("/")
    async def index(self, req: Request) -> Response:
        return req.res.text("desktop home")
""",
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize("mode", ["dev", "prod"])
def test_a_real_server_starts_answers_and_stops(make_app, monkeypatch, tmp_path, mode):
    name, _ = make_app.package(SERVER_APP)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # the child's project root
    application = importlib.import_module(f"{name}.server").App(cli_mode=True)
    desktop = application.get_extension(Desktop)
    port = _free_port()
    server = desktop.start_server(mode, port)
    try:
        desktop.wait_until_ready(server, port)
        with urllib.request.urlopen(desktop.index_url(port), timeout=5) as page:
            assert page.read() == b"desktop home"
    finally:
        desktop.stop_server(server)
    assert server.poll() is not None
    # Nothing is left listening: the whole process group was stopped.
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()


# ---- run_in_window: the server in this process, for packaged applications ---------


@pytest.fixture
def window_env(monkeypatch, tmp_path):
    """run_in_window sets these; monkeypatch restores them afterwards."""
    for name in (
        "PATERA_DEBUG",
        "PATERA_HOST",
        "PATERA_PORT",
        "PATERA_LOG_FILES__PATH",
    ):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    return monkeypatch


def _app_class(make_app, monkeypatch, tmp_path, extra: str = "") -> type:
    files = dict(SERVER_APP)
    files["server.py"] += extra
    name, _ = make_app.package(files)
    return importlib.import_module(f"{name}.server").App


def test_run_in_window_serves_the_app_until_the_window_closes(
    make_app, window_env, tmp_path
):
    app_class = _app_class(make_app, window_env, tmp_path)
    seen: dict[str, Any] = {}

    def window(app, url: str, *, dev_tools: bool) -> None:
        assert threading.current_thread() is threading.main_thread()
        with urllib.request.urlopen(url, timeout=5) as page:
            seen.update(title=app.app_name, url=url, body=page.read())
        seen["dev_tools"] = dev_tools

    window_env.setattr(desktop_module, "show_window", window)
    window_env.setattr(sys, "stdout", None)  # a windowed executable has none
    desktop_module.run_in_window(app_class)
    assert sys.stdout is not None  # replaced by the null device
    sys.stdout.close()

    assert seen["body"] == b"desktop home"
    assert seen["dev_tools"] is False  # production mode: DEBUG is off
    port = int(urllib.parse.urlparse(seen["url"]).port or 0)
    assert seen["url"] == f"http://127.0.0.1:{port}/"
    assert os.environ["PATERA_DEBUG"] == "0"
    # The server stopped with the window.
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
    assert not [t for t in threading.enumerate() if t.name == "patera-desktop-server"]


def test_run_in_window_reports_a_failed_startup(make_app, window_env, tmp_path):
    failing = """

from patera import on_startup

class FailingApp(App):
    @on_startup
    async def fail(self):
        raise RuntimeError("no database")
"""
    files = dict(SERVER_APP)
    files["server.py"] += failing
    name, _ = make_app.package(files)
    app_class = importlib.import_module(f"{name}.server").FailingApp
    window_env.setattr(desktop_module, "show_window", lambda app, url, dev_tools: None)
    with pytest.raises(RuntimeError, match="stopped while starting"):
        desktop_module.run_in_window(app_class)


def test_user_data_dir_per_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert desktop_module.user_data_dir("My: App") == tmp_path / "Roaming" / "My_ App"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    folder = desktop_module.user_data_dir("Notes")
    assert folder == tmp_path / "share" / "Notes" and folder.is_dir()
    monkeypatch.setattr(desktop_module.Path, "home", lambda: tmp_path / "home")
    support = tmp_path / "home" / "Library" / "Application Support"
    for platform in ("darwin", "ios"):
        monkeypatch.setattr(sys, "platform", platform)
        assert desktop_module.user_data_dir("Notes") == support / "Notes"
    monkeypatch.setattr(sys, "platform", "android")
    assert desktop_module.user_data_dir("Notes") == tmp_path / "home" / "Notes"


# ---- desktop:package --------------------------------------------------------------


@pytest.fixture
def packaged(make_app, monkeypatch, tmp_path):
    """An application in a package, and PyInstaller replaced by a recorder."""
    from patera.desktop import packaging

    name, folder = make_app.package(SERVER_APP)
    application = importlib.import_module(f"{name}.server").App(cli_mode=True)
    calls: list[dict[str, Any]] = []

    def fake_run(command, cwd, check):
        calls.append({"command": command, "cwd": cwd})
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(packaging, "pyinstaller_installed", lambda: True)
    monkeypatch.setattr(packaging.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    return application, name, folder, calls


def _option(command: list[str], name: str) -> list[str]:
    return [command[i + 1] for i, part in enumerate(command) if part == name]


class _SpecRun:
    """Runs a spec file with stand-ins for PyInstaller's build classes."""

    def __init__(self, spec_file: Path, work: Path, monkeypatch) -> None:
        import types

        hooks = types.ModuleType("PyInstaller.utils.hooks")
        hooks.collect_submodules = lambda name: [f"{name}.<all>"]  # type: ignore[attr-defined]
        hooks.collect_data_files = lambda name: [(f"<{name} files>", name)]  # type: ignore[attr-defined]
        for name in ("PyInstaller", "PyInstaller.utils"):
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
        monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)
        self.calls: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}

        def recorder(kind: str):
            def build(*args: Any, **kwargs: Any) -> Any:
                self.calls[kind] = (args, kwargs)
                return types.SimpleNamespace(
                    pure="pure", scripts="scripts", binaries="bins", datas="datas"
                )

            return build

        exec(
            compile(spec_file.read_text(encoding="utf-8"), str(spec_file), "exec"),
            {
                "SPECPATH": str(spec_file.parent),
                "workpath": str(work),
                **{
                    k: recorder(k)
                    for k in ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE")
                },
            },
        )

    def analysis(self) -> dict[str, Any]:
        args, kwargs = self.calls["Analysis"]
        return {"scripts": args[0], **kwargs}


def test_package_builds_with_a_generated_spec_file(packaged, tmp_path, monkeypatch):
    application, name, folder, calls = packaged
    application.run_cli("desktop:package")
    build = tmp_path / "build" / "desktop"
    spec_file = build / "desktop.spec"
    assert calls[0]["command"] == [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_file),
        "--noconfirm",
        "--distpath",
        str(tmp_path / "dist" / "desktop"),
        "--workpath",
        str(build / "work"),
    ]
    assert not (tmp_path / "desktop.spec").exists()

    run = _SpecRun(spec_file, tmp_path / "work", monkeypatch)
    analysis = run.analysis()
    entry = Path(analysis["scripts"][0])
    assert entry == tmp_path / "work" / "desktop_main.py"
    assert f"from {name}.server import App" in entry.read_text()
    assert "run_in_window(App)" in entry.read_text()
    package_folder = folder.resolve()
    assert analysis["pathex"] == [str(package_folder.parent)]
    assert (str(package_folder / "server.py"), name) in analysis["datas"]
    assert (str(package_folder / "api" / "home_api.py"), f"{name}/api") in analysis[
        "datas"
    ]
    assert ("<patera.desktop files>", "patera.desktop") in analysis["datas"]
    assert analysis["hiddenimports"] == [f"{name}.<all>", "uvicorn.<all>"]
    assert analysis["excludes"] == ["mypy", "pytest", "_pytest"]
    hooks = Path(analysis["hookspath"][0])
    assert (hooks / "pre_safe_import_module" / "hook-patera.py").is_file()
    assert run.calls["EXE"][1]["console"] is False
    assert run.calls["EXE"][1]["exclude_binaries"] is True
    assert run.calls["COLLECT"][1]["name"] == "Patera app"


def test_runtime_files_of_the_package_are_not_copied(tmp_path):
    from types import SimpleNamespace

    from patera.desktop.packaging import package_excludes, package_files

    package = tmp_path / "shop"
    for relative in (
        "__init__.py",
        "api/orders_api.py",
        "api/__pycache__/orders_api.cpython-313.pyc",
        "templates/index.html",
        "static/site.css",
        "static/uploads/photo.png",
        "logs/patera.jsonl",
        "var/log/app.jsonl",
        "shop.db",
        "shop.db-journal",
        ".env",
        ".mypy_cache/x.json",
    ):
        (package / relative).parent.mkdir(parents=True, exist_ok=True)
        (package / relative).write_text("x", encoding="utf-8")

    # The application's log folder is excluded wherever LOG_FILES.PATH puts it.
    app = SimpleNamespace(
        log_files=SimpleNamespace(path=package / "var" / "log" / "app.jsonl")
    )
    excludes = package_excludes(app, package)
    assert "var/log" in excludes and excludes.count("logs") == 1
    files = package_files(str(tmp_path), "shop", [*excludes, "static/uploads"])
    assert files == [
        (str(package / "__init__.py"), "shop"),
        (str(package / "api" / "orders_api.py"), "shop/api"),
        (str(package / "static" / "site.css"), "shop/static"),
        (str(package / "templates" / "index.html"), "shop/templates"),
    ]

    # Log files in the package folder itself: the file and its rotated copies.
    app.log_files.path = package / "app.jsonl"
    assert package_excludes(app, package)[-2:] == ["app.jsonl", "app.*.jsonl"]
    app.log_files.path = tmp_path / "elsewhere" / "app.jsonl"
    assert "app.jsonl" not in package_excludes(app, package)


def test_spec_writes_a_spec_file_to_edit(packaged, tmp_path, monkeypatch, capsys):
    application, name, folder, calls = packaged
    application.run_cli("desktop:spec")
    spec_file = tmp_path / "desktop.spec"
    assert "Wrote desktop.spec" in capsys.readouterr().out
    text = spec_file.read_text(encoding="utf-8")
    assert 'NAME = "Patera app"' in text
    assert f'APP_MODULE = "{name}.server"' in text

    # Writing it again would lose the edits.
    spec_file.write_text(text + "# edited\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        application.get_extension(Desktop).write_spec()
    assert spec_file.read_text(encoding="utf-8").endswith("# edited\n")

    # Edited settings change the build.
    (tmp_path / "start.py").write_text("print('mine')\n", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    for old, new in (
        ("HIDDEN_IMPORTS = []", 'HIDDEN_IMPORTS = ["plugins.extra"]'),
        ("DATAS = []", 'DATAS = [("assets", "assets")]'),
        ("ONE_FILE = False", "ONE_FILE = True"),
        ("CONSOLE = False", "CONSOLE = True"),
        ("ENTRY_SCRIPT = None", 'ENTRY_SCRIPT = "start.py"'),
        ("ICON = None", 'ICON = "icon.ico"'),
    ):
        assert old in text
        text = text.replace(old, new)
    spec_file.write_text(text, encoding="utf-8")
    run = _SpecRun(spec_file, tmp_path / "work", monkeypatch)
    analysis = run.analysis()
    assert analysis["scripts"] == [str(tmp_path / "start.py")]
    assert not (tmp_path / "work" / "desktop_main.py").exists()
    assert analysis["hiddenimports"][0] == "plugins.extra"
    assert (str(tmp_path / "assets"), "assets") in analysis["datas"]
    exe_args, exe_kwargs = run.calls["EXE"]
    assert exe_args[2:4] == ("bins", "datas")
    assert exe_kwargs["console"] is True
    assert exe_kwargs["icon"] == str(tmp_path / "icon.ico")
    assert "COLLECT" not in run.calls

    # desktop:package builds with the project's spec file.
    application.run_cli("desktop:package")
    assert calls[-1]["command"][3] == str(spec_file)


def test_package_builds_with_a_given_spec_file(packaged, tmp_path):
    application, _, _, calls = packaged
    desktop = application.get_extension(Desktop)
    with pytest.raises(FileNotFoundError):
        desktop.package(spec="specs/windows.spec")
    assert calls == []
    desktop.write_spec("specs/windows.spec")
    text = (tmp_path / "specs" / "windows.spec").read_text(encoding="utf-8")
    assert 'PACKAGE_PARENT = ".."' in text
    desktop.package(spec="specs/windows.spec")
    assert calls[0]["command"][3] == str(tmp_path / "specs" / "windows.spec")


def test_package_writes_to_the_given_folder(packaged, tmp_path):
    application, _, _, calls = packaged
    application.run_cli("desktop:package", command_args=["out/desk"])
    assert _option(calls[0]["command"], "--distpath") == [
        str(tmp_path / "out" / "desk")
    ]


def test_package_explains_what_is_missing(packaged, monkeypatch):
    from patera.desktop import packaging

    application, _, _, _ = packaged
    desktop = application.get_extension(Desktop)
    monkeypatch.setattr(packaging, "pyinstaller_installed", lambda: False)
    with pytest.raises(RuntimeError, match=r"patera-desktop\[pyinstaller\]"):
        desktop.package()
    monkeypatch.setattr(packaging, "pyinstaller_installed", lambda: True)
    monkeypatch.setattr(
        packaging.subprocess,
        "run",
        lambda command, cwd, check: subprocess.CompletedProcess(command, 2),
    )
    with pytest.raises(RuntimeError, match="exit code 2"):
        desktop.package()


def test_the_pyinstaller_hook_names_every_patera_folder():
    import runpy

    import patera
    from patera.desktop import packaging

    hook = runpy.run_path(
        str(packaging.HOOKS_FOLDER / "pre_safe_import_module" / "hook-patera.py")
    )
    added: list[str] = []

    class Api:
        def append_package_path(self, path):
            added.append(path)

    hook["pre_safe_import_module"](Api())
    assert added == list(patera.__path__)
    # In the workspace, the extensions live in folders of their own.
    assert len(added) > 1


def test_run_in_window_loads_the_installation_settings(make_app, window_env, tmp_path):
    app_class = _app_class(make_app, window_env, tmp_path)
    window_env.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    data_folder = tmp_path / "share" / "Patera app"
    data_folder.mkdir(parents=True)
    window_env.setattr(desktop_module, "user_data_dir", lambda name: data_folder)
    for name in ("PATERA_GREETING", "PATERA_THEME"):
        window_env.setenv(name, "")
        window_env.delenv(name)
    window_env.setenv("PATERA_THEME", "from the environment")

    settings = desktop_module.settings_file("Patera app")
    assert settings == tmp_path / "share" / "Patera app" / "settings.env"
    settings.write_text(
        "PATERA_DEBUG=1\nPATERA_GREETING=from the file\nPATERA_THEME=from the file\n"
    )
    seen: dict[str, Any] = {}

    def window(app, url: str, *, dev_tools: bool) -> None:
        seen.update(
            debug=os.environ["PATERA_DEBUG"],
            greeting=os.environ.get("PATERA_GREETING"),
            theme=os.environ.get("PATERA_THEME"),
        )

    window_env.setattr(desktop_module, "show_window", window)
    desktop_module.run_in_window(app_class)
    # The file's values apply (also over the production default), but a
    # real environment variable wins, as it does over .env.
    assert seen == {
        "debug": "1",
        "greeting": "from the file",
        "theme": "from the environment",
    }


def test_run_in_window_works_without_a_settings_file(make_app, window_env, tmp_path):
    app_class = _app_class(make_app, window_env, tmp_path)
    window_env.setenv("XDG_DATA_HOME", str(tmp_path / "empty"))
    data_folder = tmp_path / "empty" / "Patera app"
    data_folder.mkdir(parents=True)
    window_env.setattr(desktop_module, "user_data_dir", lambda name: data_folder)
    window_env.setattr(desktop_module, "show_window", lambda app, url, dev_tools: None)
    desktop_module.run_in_window(app_class)
    assert os.environ["PATERA_DEBUG"] == "0"


def test_the_spec_file_bundles_desktop_env(packaged, tmp_path, monkeypatch):
    application, _, _, calls = packaged
    application.run_cli("desktop:package")
    spec_file = tmp_path / "build" / "desktop" / "desktop.spec"
    assert 'ENV_FILE = "../../desktop.env"' in spec_file.read_text(encoding="utf-8")
    run = _SpecRun(spec_file, tmp_path / "work", monkeypatch)
    assert not [d for d in run.analysis()["datas"] if d[0].endswith("desktop.env")]

    (tmp_path / "desktop.env").write_text("PATERA_THEME=dark\n", encoding="utf-8")
    run = _SpecRun(spec_file, tmp_path / "work", monkeypatch)
    assert (str(tmp_path / "desktop.env"), ".") in run.analysis()["datas"]
