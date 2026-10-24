"""DOM-independent update scheduling and opt-in aggregate diagnostics."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from weakref import WeakSet


class Diagnostics:
    """Bounded aggregate measurements; no retained components or event objects."""

    def __init__(self, enabled=False):
        self.enabled = enabled
        self.tasks = WeakSet()
        self.reset()

    def track_task(self, task):
        if self.enabled:
            self.tasks.add(task)
        return task

    def reset(self):
        self.counts = {}
        self.timings = {}

    def count(self, name, amount=1):
        if self.enabled:
            self.counts[name] = self.counts.get(name, 0) + amount

    @contextmanager
    def measure(self, name):
        if not self.enabled:
            yield
            return
        start = perf_counter()
        try:
            yield
        finally:
            elapsed = (perf_counter() - start) * 1000
            entry = self.timings.setdefault(
                name, dict(count=0, total_ms=0.0, max_ms=0.0)
            )
            entry["count"] += 1
            entry["total_ms"] += elapsed
            entry["max_ms"] = max(entry["max_ms"], elapsed)

    def snapshot(self):
        return {
            "enabled": self.enabled,
            "counts": dict(self.counts),
            "timings": {name: dict(value) for name, value in self.timings.items()},
        }


class UpdateQueue:
    """One scheduled callback, ordered components, deduplicated binding names."""

    def __init__(self, commit, schedule, *, limit=100):
        self.commit, self.schedule, self.limit = commit, schedule, limit
        self.pending = {}
        self.cancel_scheduled = None
        self.draining = False
        self.closed = False

    def add(self, instance, binding):
        if self.closed or instance.scope.closed:
            return
        self.pending.setdefault(instance, set()).add(binding)
        if self.cancel_scheduled is None and not self.draining:
            self.cancel_scheduled = self.schedule(self.drain)

    def discard(self, instance):
        self.pending.pop(instance, None)
        if not self.pending:
            self._cancel()

    def _cancel(self):
        if self.cancel_scheduled:
            self.cancel_scheduled()
            self.cancel_scheduled = None

    def drain(self):
        if self.draining or self.closed:
            return
        self._cancel()
        self.draining = True
        try:
            for _ in range(self.limit):
                if not self.pending:
                    return
                batch, self.pending = self.pending, {}
                for instance, bindings in batch.items():
                    if self.closed:
                        return
                    if not instance.scope.closed:
                        self.commit(instance, bindings)
            self.pending.clear()
            raise RuntimeError("UI update loop exceeded the batch limit")
        finally:
            self.draining = False

    def close(self):
        self.closed = True
        self.pending.clear()
        self._cancel()
