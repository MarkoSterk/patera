"""The UI runner keeps the GUI on the main thread and owns its watcher."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from patera.desktop import Desktop
from patera.desktop.ui.server import DesktopUICLI


def make_cli(build, run):
    desktop = SimpleNamespace(run=run)

    def get_extension(kind):
        assert kind is Desktop
        return desktop

    return DesktopUICLI(
        SimpleNamespace(get_extension=get_extension),
        SimpleNamespace(build=build, output="build/ui"),
    )


@pytest.mark.parametrize("failure", [None, RuntimeError, KeyboardInterrupt])
async def test_run_builds_watches_on_worker_and_cleans_up(monkeypatch, failure):
    main = threading.get_ident()
    revision = [0]
    rebuilt = threading.Event()
    calls = []
    workers = []

    def build():
        calls.append(threading.get_ident())
        if len(calls) > 1:
            workers.append(threading.current_thread())
            rebuilt.set()
        return {"id": str(len(calls))}

    def run(mode):
        assert mode == "dev"
        assert threading.get_ident() == main
        assert calls == [main]
        revision[0] = 1
        assert rebuilt.wait(3), "Watcher did not rebuild while GUI was running"
        if failure:
            raise failure("desktop stopped")

    cli = make_cli(build, run)
    monkeypatch.setattr(cli, "_snapshot", lambda: revision[0])
    if failure:
        with pytest.raises(failure):
            await cli.run()
    else:
        await cli.run()
    assert calls[1] != main
    assert workers and all(not worker.is_alive() for worker in workers)


async def test_prod_builds_without_watching(monkeypatch):
    calls = []
    cli = make_cli(lambda: calls.append("build") or {"id": "test"}, calls.append)
    monkeypatch.setattr(cli, "_watch", lambda *args: pytest.fail("Unexpected watcher"))
    monkeypatch.setattr(cli, "_snapshot", lambda: pytest.fail("Unexpected snapshot"))
    await cli.run("prod")
    assert calls == ["build", "prod"]


async def test_initial_build_failure_does_not_launch_desktop(monkeypatch):
    def fail():
        raise FileNotFoundError("runtime.json")

    cli = make_cli(fail, lambda mode: pytest.fail("Desktop launched without a build"))
    monkeypatch.setattr(cli, "_snapshot", lambda: ())
    with pytest.raises(FileNotFoundError):
        await cli.run()


async def test_invalid_mode_does_not_build():
    cli = make_cli(lambda: pytest.fail("Unexpected build"), lambda mode: None)
    with pytest.raises(ValueError, match="dev.*prod"):
        await cli.run("invalid")


def test_watcher_recovers_after_failed_build(monkeypatch, capsys):
    stop = threading.Event()
    revisions = iter(["broken", "fixed"])
    attempts = []

    def build():
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("invalid template")
        stop.set()
        return {"id": "fixed"}

    cli = make_cli(build, lambda mode: None)
    monkeypatch.setattr(cli, "_snapshot", lambda: next(revisions))
    cli._watch(stop)
    assert len(attempts) == 2
    output = capsys.readouterr().out
    assert "previous build retained" in output
    assert "Built UI fixed" in output


async def test_standalone_watch_joins_worker_on_cancellation(monkeypatch):
    started = threading.Event()
    workers = []
    cli = make_cli(lambda: {"id": "test"}, lambda mode: None)

    def watch(stop):
        workers.append(threading.current_thread())
        started.set()
        stop.wait(3)

    monkeypatch.setattr(cli, "_watch", watch)
    task = asyncio.create_task(cli.watch())
    while not started.is_set():
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert workers and not workers[0].is_alive()
