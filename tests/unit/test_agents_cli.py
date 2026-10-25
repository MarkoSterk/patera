"""Observable installation behavior and executable examples for agent guidance."""

import re
import sys
from importlib.resources import files

import pytest

from patera.cli.agents import END, START, generate_agents
from patera.cli.cli import main


def invoke(monkeypatch, root, *args):
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["patera", "agents", *args])
    return main()


@pytest.mark.parametrize("profile", [None, "codex", "claude", "all"])
def test_profiles_work_without_application(tmp_path, monkeypatch, profile):
    from patera.cli import cli

    def unexpected(*args, **kwargs):
        pytest.fail("Scaffolding must not load an application")

    monkeypatch.setitem(cli.methods, "cli", unexpected)
    monkeypatch.setenv("PATERA_IMPORT", "missing.module:App")
    args = () if profile is None else (profile,)
    assert invoke(monkeypatch, tmp_path, *args) == 0
    codex = profile in (None, "codex", "all")
    claude = profile in ("claude", "all")
    assert (tmp_path / "AGENTS.md").exists() == codex
    assert (tmp_path / "CLAUDE.md").exists() == claude
    for enabled, folder in [(codex, ".agents"), (claude, ".claude")]:
        skill = tmp_path / folder / "skills/patera/SKILL.md"
        assert skill.exists() == enabled
        if enabled:
            # Every routed reference must be available in a downstream project.
            links = re.findall(r"\]\((references/[^)]+)\)", skill.read_text())
            assert links
            for relative in links:
                assert (skill.parent / relative).is_file()
    if profile == "all":
        assert "@AGENTS.md" in (tmp_path / "CLAUDE.md").read_text()
        a = tmp_path / ".agents/skills/patera"
        b = tmp_path / ".claude/skills/patera"
        for source in a.rglob("*.md"):
            assert source.read_bytes() == (b / source.relative_to(a)).read_bytes()


def test_rerun_is_noop_preserving_user_text_and_mtimes(tmp_path):
    instructions = tmp_path / "AGENTS.md"
    original = b"# Project\r\n\r\nKeep our conventions.\r\n"
    instructions.write_bytes(original)
    assert generate_agents(tmp_path) == 0
    instructions.write_bytes(
        instructions.read_bytes() + b"\r\n## Personal notes\r\nKeep these.\r\n"
    )
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*.md")}
    assert generate_agents(tmp_path) == 0
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    assert instructions.read_bytes().startswith(original)
    assert instructions.read_bytes().endswith(b"Keep these.\r\n")


def test_existing_managed_section_updates_only_inside_markers(tmp_path):
    instructions = tmp_path / "CLAUDE.md"
    before = "# My project\n\n"
    after = "\n\nMy rules stay here."
    instructions.write_text(before + START + "\nOld guidance\n" + END + after)
    assert generate_agents(tmp_path, "all") == 0
    assert instructions.read_text() == before + START + "\n@AGENTS.md\n" + END + after


def test_conflicts_preflight_everything_and_force_preserves_unrelated_files(tmp_path):
    skill = tmp_path / ".agents/skills/patera/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("My custom skill")
    other = skill.parent / "personal.md"
    other.write_text("Keep me")
    assert generate_agents(tmp_path, "all") == 1
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".claude").exists()
    assert skill.read_text() == "My custom skill"
    assert generate_agents(tmp_path, "all", force=True) == 0
    assert skill.read_text() != "My custom skill"
    assert other.read_text() == "Keep me"


def test_dry_run_never_writes_even_with_force(tmp_path, monkeypatch, capsys):
    assert invoke(monkeypatch, tmp_path, "all", "--dry-run") == 0
    assert list(tmp_path.iterdir()) == []
    assert "Would write" in capsys.readouterr().out
    generate_agents(tmp_path)
    skill = tmp_path / ".agents/skills/patera/SKILL.md"
    skill.write_text("Custom")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.md")}
    assert invoke(monkeypatch, tmp_path, "--dry-run") == 1
    assert invoke(monkeypatch, tmp_path, "--dry-run", "--force") == 0
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.md")}


@pytest.mark.parametrize("content", [START, END, END + START, START + END + START])
def test_malformed_markers_are_not_overwritten_even_with_force(tmp_path, content):
    path = tmp_path / "AGENTS.md"
    path.write_text(content)
    assert generate_agents(tmp_path, force=True) == 1
    assert path.read_text() == content
    assert not (tmp_path / ".agents").exists()


@pytest.mark.parametrize("relative", ["AGENTS.md", ".agents/skills/patera/SKILL.md"])
def test_directory_in_place_of_file_is_a_conflict(tmp_path, relative):
    (tmp_path / relative).mkdir(parents=True)
    assert generate_agents(tmp_path, force=True) == 1
    assert not (tmp_path / ".agents/skills/patera/references").exists()


def test_file_in_place_of_parent_is_a_conflict(tmp_path):
    (tmp_path / ".agents").write_text("Keep me")
    assert generate_agents(tmp_path, force=True) == 1
    assert not (tmp_path / "AGENTS.md").exists()


def test_linked_destinations_are_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    try:
        (project / ".agents").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    assert generate_agents(project, force=True) == 1
    assert list(outside.iterdir()) == []
    assert not (project / "AGENTS.md").exists()


@pytest.mark.parametrize("args", [("unknown",), ("codex", "extra"), ("--unknown",)])
def test_bad_arguments_exit_without_writes(tmp_path, monkeypatch, args):
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, tmp_path, *args)
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_help_does_not_load_app_or_write(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, tmp_path, "--help")
    assert exc.value.code == 0
    assert "--dry-run" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_top_level_help_lists_agents(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["patera", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert "agents" in capsys.readouterr().out


def test_cli_agents_is_no_longer_a_scaffolding_alias(tmp_path, monkeypatch):
    from patera.cli import cli

    captured = {}
    monkeypatch.setitem(
        cli.methods, "cli", lambda cwd, **kwargs: captured.update(kwargs)
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["patera", "cli", "agents", "claude"])
    main()
    assert captured["command_name"] == "agents"
    assert captured["command_args"] == ["claude"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "option", [["--app", "missing:App"], ["--env-file", "missing"], ["--list"]]
)
def test_app_only_options_are_rejected(tmp_path, monkeypatch, option):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["patera", "agents", *option])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []


def example(topic):
    text = (
        files("patera.cli")
        .joinpath("agent_templates", "references", topic + ".md")
        .read_text(encoding="utf-8")
    )
    code = re.search(r"```python\n(.*?)```", text, re.DOTALL).group(1)
    namespace = {"__name__": "agent_example"}
    exec(compile(code, topic + ".md", "exec"), namespace)  # noqa: S102 - trusted bundled examples
    return namespace


async def test_documented_controller_and_service_examples_run(make_app, client_for):
    routes = example("controllers-routing")
    services = example("dependency-injection")
    app = make_app(controllers=[routes["NotesController"], services["HelloController"]])
    async with client_for(app) as client:
        response = await client.post("/notes/", json={"title": "Example"})
        assert response.status_code == 201
        assert response.json() == {"title": "Example"}
        assert (await client.post("/notes/", json={})).status_code == 422
        assert (await client.get("/notes/3")).json() == {"id": 3}
        assert (await client.get("/hello/Ada")).json() == {"message": "Hello, Ada!"}


def test_documented_cli_example_runs(make_app, capsys):
    ns = example("cli-controllers")
    app = make_app(cli_mode=True)
    app.register_cli_controller(ns["GreetingCLI"](app))
    app.run_cli("greetings:repeat", command_args=["Ada", "2"])
    assert capsys.readouterr().out.count("Hello, Ada!") == 2


async def test_documented_middleware_and_error_handler_work(make_app, client_for):
    from patera import Request, Response
    from patera.controller import Controller, get, path

    errors = example("error-handlers")
    middleware = example("middleware")

    @path("/example")
    class ExampleController(Controller):
        @get("/ok")
        async def ok(self, req: Request) -> Response:
            return req.res.json({"ok": True})

        @get("/missing")
        async def missing(self, req: Request) -> Response:
            raise errors["MissingNote"]("No such note")

    app = make_app(
        controllers=[ExampleController],
        middleware=[middleware["TraceMiddleware"]],
        exception_handlers=[errors["ApplicationErrors"]],
        extensions=[example("extensions")["AuditService"]],
    )
    async with client_for(app) as client:
        assert (await client.get("/example/ok")).headers["X-Trace-Source"] == "http"
        response = await client.get("/example/missing")
        assert response.status_code == 404
        assert response.json()["title"] == "Note not found"


async def test_documented_joltui_example_runs(make_app, client_for):
    ns = example("joltui")
    app = make_app(extensions=[ns["JoltuiInterface"]])
    async with client_for(app) as client:
        response = await client.post(
            "/joltui/components",
            json={
                "tagName": "user-page",
                "groupName": "user-group",
                "routeParameters": {"user_id": "42"},
            },
        )
        assert response.status_code == 200
        assert response.text == "<h1>User 42</h1>"
        assert response.headers["content-type"].startswith("text/html")
        response = await client.post(
            "/joltui/components",
            json={
                "tagName": "user-page",
                "groupName": "user-group",
                "routeParameters": {"user_id": "invalid"},
            },
        )
        assert response.status_code == 422
