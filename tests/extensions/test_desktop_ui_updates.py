"""Contracts for batching, fragment identity, and bounded diagnostics."""

import asyncio
from types import SimpleNamespace

import pytest

from patera.desktop.ui import Application, Component, TemplateEngine, template
from patera.desktop.ui.updates import Diagnostics, UpdateQueue


def queue_fixture(commit, limit=100):
    scheduled, cancelled = [], []

    def schedule(callback):
        scheduled.append(callback)
        return lambda: cancelled.append(True)

    return UpdateQueue(commit, schedule, limit=limit), scheduled, cancelled


async def test_queue_deduplicates_and_flush_does_not_wait_for_frame():
    app = Application(batch_updates=True)
    component = Component(app, None)
    calls = []
    queue, scheduled, cancelled = queue_fixture(
        lambda item, keys: calls.append((item, keys))
    )
    app.adapter = SimpleNamespace(updates=queue)
    for _ in range(100):
        queue.add(component, "count")
    queue.add(component, "other")
    assert len(scheduled) == 1
    assert calls == []
    await app.flush()
    assert calls == [(component, {"count", "other"})]
    assert cancelled == [True]
    assert not queue.pending


async def test_queue_discard_and_disposal_during_batch():
    app = Application()
    first, second = Component(app, None), Component(app, None)
    calls = []

    def commit(item, keys):
        calls.append(item)
        second.scope.cancel()

    queue, _, _ = queue_fixture(commit)
    queue.add(first, "a")
    queue.add(second, "b")
    queue.drain()
    assert calls == [first]
    queue.add(first, "c")
    queue.discard(first)
    assert not queue.pending
    queue.close()
    queue.add(first, "d")
    assert not queue.pending


def test_render_triggered_invalidations_are_later_batches_and_guarded():
    component = Component(Application(), None)
    calls = []

    def commit(item, bindings):
        calls.append(bindings)
        queue.add(item, "again")

    queue, _, _ = queue_fixture(commit, limit=3)
    queue.add(component, "first")
    with pytest.raises(RuntimeError, match="batch limit"):
        queue.drain()
    assert calls == [{"first"}, {"again"}, {"again"}]
    assert not queue.pending
    assert not queue.draining


def test_parent_dominates_child_and_unchanged_preserves_anchor_ids():
    state = SimpleNamespace(value=1)
    _, renderer = TemplateEngine().render(
        template(
            '<div data-bind="parent"><b data-bind="child">{{ state.value }}</b></div>',
            state=state,
        )
    )
    original = dict(renderer.parents)
    assert renderer.refresh_many({"parent", "child"}, skip_unchanged=True) == []
    assert renderer.parents == original
    state.value = 2
    changes = renderer.refresh_many({"parent", "child"}, skip_unchanged=True)
    assert len(changes) == 1
    assert changes[0][0] == "1"
    assert renderer.parents == original
    state.value = 3
    assert renderer.refresh_many({"child"}, skip_unchanged=True) == [("2", "3")]
    assert renderer.refresh_many({"parent"}, skip_unchanged=True) == []
    # Reverting via the parent must not mistake its old cached output for the DOM.
    state.value = 2
    assert len(renderer.refresh_many({"parent"}, skip_unchanged=True)) == 1


def test_equal_output_replaces_loop_closures_and_transaction_rolls_back():
    state = SimpleNamespace(rows=[SimpleNamespace(value=1)])
    _, renderer = TemplateEngine().render(
        template(
            '<div data-bind="rows">{% for row in state.rows %}'
            '<b data-bind="row">{{ row.value }}</b>{% endfor %}</div>',
            state=state,
        )
    )
    state.rows = [SimpleNamespace(value=1)]
    assert renderer.refresh_many({"rows"}, skip_unchanged=True) == []
    state.rows[0].value = 2
    assert renderer.refresh("row") == [("2", "2")]
    snapshot = (
        dict(renderer.fragments),
        dict(renderer.parents),
        dict(renderer.outputs),
    )
    state.rows = [SimpleNamespace()]
    with pytest.raises(Exception):
        renderer.refresh_many({"rows"}, skip_unchanged=True)
    assert (renderer.fragments, renderer.parents, renderer.outputs) == snapshot
    assert renderer.stack == []


def test_diagnostics_disabled_and_snapshot_independent():
    diagnostics = Diagnostics()
    with diagnostics.measure("template"):
        diagnostics.count("writes")
    assert diagnostics.snapshot() == dict(enabled=False, counts={}, timings={})
    diagnostics.enabled = True
    with diagnostics.measure("template"):
        diagnostics.count("writes", 2)
    snapshot = diagnostics.snapshot()
    assert snapshot["counts"]["writes"] == 2
    assert snapshot["timings"]["template"]["count"] == 1
    diagnostics.reset()
    assert snapshot["counts"]["writes"] == 2
    assert diagnostics.snapshot()["counts"] == {}


def test_selected_parent_can_remove_every_selected_child():
    state = SimpleNamespace(rows=[1, 2])
    _, renderer = TemplateEngine().render(
        template(
            '<div data-bind="rows">{% for row in state.rows %}'
            '<b data-bind="row">{{ row }}</b>{% endfor %}</div>',
            state=state,
        )
    )
    state.rows = []
    assert renderer.refresh_many({"rows", "row"}, skip_unchanged=True) == [("1", "")]
    assert list(renderer.fragments) == ["1"]


async def test_obsolete_render_cannot_commit_and_dispose_is_idempotent():
    app = Application()
    started, release = asyncio.Event(), asyncio.Event()
    committed = []

    class Slow(Component):
        calls = 0

        async def markup(self):
            self.calls += 1
            if self.calls == 1:
                started.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
                return "obsolete"
            return "current"

    async def render(instance, markup, renderer):
        committed.append(markup)

    async def children(instance):
        pass

    queue, _, _ = queue_fixture(lambda *_: None)
    app.adapter = SimpleNamespace(
        render_component=render, wait_children=children, updates=queue
    )
    component = Slow(app, None)
    old = asyncio.create_task(component.rerender())
    await started.wait()
    await component.rerender()
    release.set()
    await old
    assert committed == ["current"]
    cleaned = []
    component.on_cleanup(lambda: cleaned.append(True))
    queue.add(component, "count")
    await component.dispose()
    await component.dispose()
    assert cleaned == [True]
    assert not queue.pending
    assert component._renderer is None


async def test_concurrent_disposal_waits_for_cleanup_once():
    started, release = asyncio.Event(), asyncio.Event()
    component = Component(Application(), None)
    calls = []

    async def cleanup():
        calls.append(True)
        started.set()
        # Reentrant disposal by a cleanup hook must not wait on itself.
        await component.dispose()
        await release.wait()

    component.on_cleanup(cleanup)
    first = asyncio.create_task(component.dispose())
    await started.wait()
    second = asyncio.create_task(component.dispose())
    await asyncio.sleep(0)
    assert not second.done()
    release.set()
    await asyncio.gather(first, second)
    assert calls == [True]
