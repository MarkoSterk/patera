"""The optional UI boundary, routing, artifacts and desktop integration."""

import asyncio
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from jinja2 import TemplateNotFound

from patera.controller import Controller as HTTPController, get, path as http_path
from patera.desktop.ui import (
    Application,
    Controller,
    DesktopUI,
    DesktopUIConfig,
    ExceptionHandler,
    NoRouteMatch,
    State,
    View,
    handles,
    html,
    page,
    path,
    trusted_html,
)
from patera.desktop.ui.build import build, lock_runtime
from patera.desktop.ui.routing import Router


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "frontend"
    (source / "frontend").mkdir(parents=True)
    (source / "frontend" / "__init__.py").write_text(
        "from patera.desktop.ui import Application\napp = Application(controllers=[])\n"
    )
    (source / "templates").mkdir()
    (source / "templates" / "note.html").write_text("<h1>{{ title }}</h1>")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "core.js").write_text("// test runtime")
    (runtime / "pyodide.mjs").write_text("// test interpreter")
    lock_runtime(
        runtime,
        pyscript="core.js",
        interpreter="pyodide.mjs",
        pyscript_version="test",
        pyodide_version="test",
        python_version="3.13",
    )
    return source, runtime, tmp_path / "output"


def do_build(inputs):
    return build(*inputs, entrypoint="frontend:app", asset_url="/prefix/__ui__")


def test_bundle_is_deterministic_and_runs_without_native_dependencies(inputs, tmp_path):
    first = do_build(inputs)
    second = do_build(inputs)
    assert first == second
    bundle = inputs[2] / first["id"] / "patera-ui.zip"
    with zipfile.ZipFile(bundle) as archive:
        assert archive.read("patera/__init__.py") == b""
        assert not any(
            "server.py" in name or "build.py" in name for name in archive.namelist()
        )
        assert (
            json.loads(archive.read("ui.json"))["templates"]["templates/note.html"]
            == "<h1>{{ title }}</h1>"
        )
    script = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(bundle)!r})",
            "from frontend import app",
            "from patera.desktop.ui import Controller",
            "assert not any(n in sys.modules for n in ('pydantic', 'webview', 'patera.patera', 'js', 'pyscript'))",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_build_excludes_private_and_generated_files(inputs):
    source = inputs[0]
    for name in (".env", "secret.db", "cache.pyc", "values.json"):
        (source / name).write_text("secret")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "bad.py").write_text("invalid syntax!")
    manifest = do_build(inputs)
    with zipfile.ZipFile(inputs[2] / manifest["id"] / "patera-ui.zip") as archive:
        assert not any(
            "secret" in name
            or "__pycache__" in name
            or name.endswith(".pyc")
            or ".env" in name
            for name in archive.namelist()
        )


def test_runtime_tampering_does_not_replace_current_build(inputs):
    manifest = do_build(inputs)
    (inputs[1] / "core.js").write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        do_build(inputs)
    assert json.loads((inputs[2] / "current.json").read_text())["id"] == manifest["id"]


def test_invalid_source_is_not_imported_and_does_not_replace_build(inputs):
    manifest = do_build(inputs)
    (inputs[0] / "frontend" / "invalid.py").write_text("invalid syntax!")
    with pytest.raises(SyntaxError):
        do_build(inputs)
    assert json.loads((inputs[2] / "current.json").read_text())["id"] == manifest["id"]


def test_source_change_produces_new_build_and_keeps_previous(inputs):
    first = do_build(inputs)
    (inputs[0] / "templates" / "note.html").write_text("New view")
    second = do_build(inputs)
    assert first["id"] != second["id"]
    assert (inputs[2] / first["id"] / "patera-ui.zip").is_file()


def test_runtime_traversal_rejected(inputs):
    runtime = inputs[1] / "runtime.json"
    data = json.loads(runtime.read_text())
    data["files"]["../outside"] = "bad"
    runtime.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Unsafe"):
        do_build(inputs)


def test_router_precedence_conversion_encoding_and_aliases():
    router = Router()

    def handler():
        pass

    router.add("/notes/<path:rest>", "all", handler)
    router.add("/notes/<int:id>", "detail", handler)
    router.add("/notes/new", "new", handler)
    router.add("/labels/<name>", "label", handler)
    assert router.match("/notes/new/")[0].endpoint == "new"
    assert router.match("/notes/12")[1] == {"id": 12}
    assert router.match("/labels/a%20b")[1] == {"name": "a b"}
    assert (
        router.url_for("label", name="a?b", query={"x": [1, 2]})
        == "/labels/a%3Fb?x=1&x=2"
    )
    with pytest.raises(ValueError):
        router.url_for("detail", id=True)
    with pytest.raises(NoRouteMatch):
        router.match("/labels/a%2Fb")
    with pytest.raises(ValueError, match="Duplicate page route"):
        router.add("/notes/<int:other>", "other", handler)


def test_escaping_and_explicit_trusted_markup():
    assert (
        html("{{ value }}", value='<img src=x onerror="bad">')
        == "&lt;img src=x onerror=&#34;bad&#34;&gt;"
    )
    assert html("{{ value }}", value=trusted_html("<b>ok</b>")) == "<b>ok</b>"
    assert html("{{ note.title }}", note={"title": "A&B"}) == "A&amp;B"
    rendered = html("{{ title }}", title="{{ user_supplied_expression }}")
    assert View(markup=rendered).render({}) == "{{ user_supplied_expression }}"


def test_state_subscription_lifetime_and_independent_values():
    events = []
    state = State(count=0)
    unsubscribe = state.subscribe(lambda key, value: events.append((key, value)))
    state["count"] = 1
    unsubscribe()
    unsubscribe()
    state["count"] = 2
    assert events == [("count", 1)]


def test_strict_slashes_are_preserved_by_controller_metadata():
    @path("/notes")
    class Pages(Controller):
        @page("/")
        def index(self, ctx):
            return View(markup="notes")

    app = Application(controllers=[Pages], strict_slashes=True)
    assert app.router.match("/notes/")[0].endpoint == "Pages.index"
    with pytest.raises(NoRouteMatch):
        app.router.match("/notes")


async def test_page_event_can_navigate_without_cancelling_itself():
    class Pages(Controller):
        @page("/one")
        @page("/two")
        def index(self, ctx):
            return View(markup="page")

    app = Application(controllers=[Pages])
    await app.navigate("/one")
    assert await app.context.spawn(app.navigate("/two"))
    assert app.context.url == "/two"
    await app.stop()


async def test_render_failure_uses_exception_handler():
    class Pages(Controller):
        @page("/")
        def index(self, ctx):
            return View("missing.html")

    called = []

    class Errors(ExceptionHandler):
        @handles(TemplateNotFound)
        def missing(self, ctx, error):
            called.append(error)
            return View(markup="Missing template")

    app = Application(controllers=[Pages], exception_handlers=[Errors])
    assert await app.navigate("/")
    assert len(called) == 1
    await app.stop()


async def test_latest_navigation_wins_even_when_handler_suppresses_cancel():
    started = asyncio.Event()
    release = asyncio.Event()
    cleaned = []

    @path("/")
    class Pages(Controller):
        @page("/slow")
        async def slow(self, ctx):
            ctx.on_cleanup(lambda: cleaned.append("slow"))
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return View(markup="slow")

        @page("/fast")
        async def fast(self, ctx):
            return View(markup="fast")

    app = Application(controllers=[Pages])
    slow = asyncio.create_task(app.navigate("/slow"))
    await started.wait()
    assert await app.navigate("/fast")
    release.set()
    assert not await slow
    assert app.context.url == "/fast"
    assert cleaned == ["slow"]
    await app.stop()


async def test_typed_exception_dispatch_and_page_cleanup():
    class Specific(ValueError):
        pass

    seen = []

    class Errors(ExceptionHandler):
        @handles(ValueError)
        def value(self, ctx, exc):
            seen.append(type(exc))
            return View(markup="error")

    class Pages(Controller):
        @page("/error")
        def error(self, ctx):
            ctx.on_cleanup(lambda: seen.append("cleanup"))
            raise Specific("problem")

    app = Application(controllers=[Pages], exception_handlers=[Errors])
    assert await app.navigate("/error?x=1&x=2")
    assert app.context.query == {"x": ["1", "2"]}
    await app.stop()
    assert seen == [Specific, "cleanup"]


@http_path("/api")
class ExampleAPI(HTTPController):
    @get("/notes")
    async def notes(self, req):
        return req.res.json([{"title": "A note"}])


def ui_app(make_app, inputs, **settings):
    source, runtime, output = inputs
    config = DesktopUIConfig(
        SOURCE=str(source), RUNTIME=str(runtime), OUTPUT=str(output), **settings
    )
    return make_app(
        extensions=[DesktopUI],
        controllers=[ExampleAPI],
        URL_PREFIX="/prefix",
        DESKTOP_UI=config,
    )


async def test_extension_registers_without_building_and_serves_assets(
    make_app, inputs, client_for
):
    app = ui_app(make_app, inputs, PUBLIC={"value": "</script><script>bad</script>"})
    extension = app.get_extension(DesktopUI)
    assert not inputs[2].exists()
    manifest = extension.build()
    async with client_for(app) as client:
        shell = await client.get("/prefix/app/notes/4", headers={"Host": "127.0.0.1"})
        assert shell.status_code == 200
        assert "</script><script>bad" not in shell.text
        assert shell.headers["cache-control"] == "no-store"
        assert '"mount": "/prefix/app"' in shell.text
        url = f"/prefix/__ui__/{manifest['id']}/patera-ui.zip"
        response = await client.get(url)
        assert response.status_code == 200
        assert "immutable" in response.headers["cache-control"]
        partial = await client.get(url, headers={"Range": "bytes=0-3"})
        assert partial.status_code == 206
        assert partial.content == b"PK\x03\x04"
        cached = await client.get(
            url, headers={"If-None-Match": response.headers["etag"]}
        )
        assert cached.status_code == 304
        missing = await client.get(f"/prefix/__ui__/{manifest['id']}/missing.js")
        assert missing.status_code == 404


async def test_api_token_origin_and_host_protection(make_app, inputs, client_for):
    app = ui_app(make_app, inputs)
    token = app.get_extension(DesktopUI).token
    async with client_for(app) as client:
        for headers in (
            {"Host": "localhost"},
            {"Host": "evil.test", "X-Patera-UI-Token": token},
            {
                "Host": "localhost",
                "X-Patera-UI-Token": token,
                "Origin": "https://evil.test",
            },
            {
                "Host": "localhost",
                "X-Patera-UI-Token": token,
                "Sec-Fetch-Site": "cross-site",
            },
        ):
            response = await client.get("/prefix/api/notes", headers=headers)
            assert response.status_code == 403
        response = await client.get(
            "/prefix/api/notes",
            headers={
                "Host": "localhost",
                "X-Patera-UI-Token": token,
                "Origin": "http://localhost",
            },
        )
        assert response.status_code == 200


def test_multiple_applications_do_not_share_controllers_or_token(make_app, inputs):
    first = ui_app(make_app, inputs).get_extension(DesktopUI)
    second = ui_app(make_app, inputs, MOUNT="/other").get_extension(DesktopUI)
    assert first.token != second.token
    assert first.mount == "/prefix/app"
    assert second.mount == "/prefix/other"
    assert (
        first.app.controllers["DesktopUIShell"].__class__
        is not second.app.controllers["DesktopUIShell"].__class__
    )


def test_packaging_contribution_builds_without_application_import(
    make_app, inputs, tmp_path
):
    from patera.desktop.packaging import desktop_contributions, prepare_desktop_assets

    app = ui_app(make_app, inputs)
    spec = tmp_path / "desktop.spec"
    entries = prepare_desktop_assets(desktop_contributions(app, spec), str(spec.parent))
    assert entries[0][1] == "patera_ui"
    assert Path(entries[0][0]).is_file()
    assert entries[1][1].startswith("patera_ui/")


def test_generated_spec_builds_ui_when_executed_directly(
    make_app, inputs, tmp_path, monkeypatch
):
    from patera.desktop.packaging import write_spec
    from tests.extensions.test_desktop import _SpecRun

    app = ui_app(make_app, inputs)
    spec = write_spec(app, tmp_path / "desktop.spec")
    run = _SpecRun(spec, tmp_path / "work", monkeypatch)
    assert any(target == "patera_ui" for _, target in run.analysis()["datas"])
    assert (inputs[2] / "current.json").is_file()


@pytest.mark.parametrize(
    "contents",
    [
        "# prepare_desktop_assets([])\n",
        "DESKTOP_ASSETS = []\ndatas = prepare_desktop_assets(DESKTOP_ASSETS, SPECPATH)\n",
    ],
)
def test_specs_created_before_ui_registration_are_rejected(
    make_app, inputs, tmp_path, contents
):
    from patera.desktop.packaging import validate_desktop_assets

    app = ui_app(make_app, inputs)
    spec = tmp_path / "old.spec"
    spec.write_text(contents)
    with pytest.raises(RuntimeError, match="missing extension asset builds"):
        validate_desktop_assets(app, spec)


def test_browser_sources_cannot_be_collected_as_backend_modules(
    make_app, inputs, tmp_path
):
    app = ui_app(make_app, inputs)
    extension = app.get_extension(DesktopUI)
    extension.configs.SOURCE = str(Path(app.root_path) / "frontend")
    with pytest.raises(ValueError, match="outside the backend"):
        extension.desktop_packaging(tmp_path / "desktop.spec")


async def test_version_endpoint_is_development_only(make_app, inputs, client_for):
    app = ui_app(make_app, inputs)
    extension = app.get_extension(DesktopUI)
    manifest = extension.build()
    async with client_for(app) as client:
        app.configs.DEBUG = True
        response = await client.get("/prefix/__ui__/version")
        assert response.json() == {"id": manifest["id"]}
        assert response.headers["cache-control"] == "no-store"
        app.configs.DEBUG = False
        response = await client.get("/prefix/__ui__/version")
        assert response.status_code == 404


def test_frozen_extension_reads_prebuilt_assets(make_app, inputs, monkeypatch):
    app = ui_app(make_app, inputs)
    extension = app.get_extension(DesktopUI)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(inputs[2]), raising=False)
    assert extension.output == inputs[2] / "patera_ui"
    with pytest.raises(RuntimeError, match="prebuilt"):
        extension.build()


@pytest.mark.parametrize(
    "settings",
    [
        {"MOUNT": "/"},
        {"ASSETS": "/app/files"},
        {"API_PATHS": ["/app"]},
        {"MOUNT": "/app?x"},
        {"PUBLIC": {"value": object()}},
    ],
)
def test_configuration_rejects_ambiguous_or_nonpublic_values(settings):
    with pytest.raises((ValueError, TypeError)):
        DesktopUIConfig(**settings)


def test_component_tag_preserves_class_and_validates_names():
    from patera.desktop.ui import Component, tag

    class Counter(Component):
        pass

    assert tag("note-counter")(Counter) is Counter
    assert Counter.tag == "note-counter"
    for invalid in ("counter", "Note-counter", "note--counter", "font-face"):
        with pytest.raises(ValueError):
            tag(invalid)
    with pytest.raises(TypeError):
        tag("not-component")(object)


def test_folder_discovery_in_isolated_browser_bundle(inputs):
    source = inputs[0] / "frontend"
    (source / "__init__.py").write_text(
        "from patera.desktop.ui import Application\n"
        "from .controllers.pages import Pages\n"
        "app = Application(__name__, controllers=[Pages])\n"
    )
    modules = {
        "controllers/pages.py": (
            "from patera.desktop.ui import Controller, PageContext, View, page, path\n"
            "@path('/')\nclass Pages(Controller):\n"
            "    @page('/')\n    def index(self, ctx: PageContext) -> View:\n"
            "        return View(markup='hello')\n"
        ),
        "components/nested/counter.py": (
            "from __future__ import annotations\n"
            "from typing import TYPE_CHECKING\n"
            "from patera.desktop.ui import Component, event, tag\n"
            "if TYPE_CHECKING:\n"
            "    from patera.desktop.ui.types import MouseEvent\n"
            "@tag('note-counter')\nclass Counter(Component):\n"
            "    @event('click')\n    def click(self, event: MouseEvent) -> None:\n"
            "        event.preventDefault()\n"
        ),
        "exceptions/errors.py": (
            "from patera.desktop.ui import ExceptionHandler, PageContext, handles\n"
            "class Errors(ExceptionHandler):\n"
            "    @handles(ValueError)\n"
            "    def error(self, ctx: PageContext | None, error: ValueError): pass\n"
        ),
        "controllers/aliases.py": "from .pages import Pages\n",
        "controllers/_ignored.py": "raise RuntimeError('private module')\n",
        "components/base.py": (
            "from abc import ABC, abstractmethod\n"
            "from patera.desktop.ui import Component\n"
            "class Base(Component, ABC):\n"
            "    @abstractmethod\n    def render(self): pass\n"
        ),
    }
    for name, content in modules.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        folder = target.parent
        while folder != source:
            (folder / "__init__.py").touch()
            folder = folder.parent
        target.write_text(content)
    artifact = do_build(inputs)
    bundle = inputs[2] / artifact["id"] / "patera-ui.zip"
    script = f"""
import sys
sys.path.insert(0, {str(bundle)!r})
from frontend import app
assert len(app.controllers) == 1
assert len(app.components) == 1
assert app.components[0].tag == 'note-counter'
assert ValueError in app.handlers
assert not any(n in sys.modules for n in ('pydantic', 'webview', 'js', 'pyscript'))
"""
    subprocess.run([sys.executable, "-I", "-S", "-c", script], check=True)


def test_discovery_surfaces_import_errors_and_allows_missing_folders(
    tmp_path, monkeypatch
):
    package = tmp_path / "ui_discovery_test"
    package.mkdir()
    (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        assert Application("ui_discovery_test").components == []
        (package / "components.py").write_text("import missing_ui_dependency_xyz")
        import importlib

        importlib.invalidate_caches()
        with pytest.raises(ModuleNotFoundError, match="missing_ui_dependency_xyz"):
            Application("ui_discovery_test")
    finally:
        for name in list(sys.modules):
            if name == "ui_discovery_test" or name.startswith("ui_discovery_test."):
                del sys.modules[name]


async def test_server_components_use_backend_jinja_and_protected_allowlist(
    make_app, inputs, client_for
):
    from jinja2 import DictLoader

    app = ui_app(
        make_app,
        inputs,
        SERVER_COMPONENTS_PATH="/api/components",
        SERVER_COMPONENTS={"default/note-preview": "preview.html"},
    )
    app.jinja_environment.loader = DictLoader(
        {"preview.html": "<b>{{ args.title }}</b>{{ extra|default('') }}"}
    )
    extension = app.get_extension(DesktopUI)
    extension.register_server_component(
        "custom-preview", "preview.html", context=lambda req, payload: {"extra": "!"}
    )
    headers = {"Host": "localhost", "X-Patera-UI-Token": extension.token}
    async with client_for(app) as client:
        payload = {"tag_name": "note-preview", "attributes": {"title": "<note>"}}
        blocked = await client.post(
            "/prefix/api/components", json=payload, headers={"Host": "localhost"}
        )
        assert blocked.status_code == 403
        response = await client.post(
            "/prefix/api/components", json=payload, headers=headers
        )
        assert response.status_code == 200
        assert response.text == "<b>&lt;note&gt;</b>"
        payload["tag_name"] = "../preview.html"
        response = await client.post(
            "/prefix/api/components", json=payload, headers=headers
        )
        assert response.status_code == 404
        payload["tag_name"] = "custom-preview"
        response = await client.post(
            "/prefix/api/components", json=payload, headers=headers
        )
        assert response.text == "<b>&lt;note&gt;</b>!"


def test_server_component_path_must_be_protected():
    with pytest.raises(ValueError, match="protected API"):
        DesktopUIConfig(SERVER_COMPONENTS_PATH="/public-components")
