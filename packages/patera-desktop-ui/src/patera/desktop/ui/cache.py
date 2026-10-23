"""Application-owned template cache and retryable lazy dependencies."""

import asyncio
import math
import time
import importlib
from .lifecycle import invoke


class DependencyLoadError(RuntimeError):
    pass


class LazyDependency:
    def __init__(self, loader, name=None):
        if isinstance(loader, str):
            module = loader

            def loader():
                return importlib.import_module(module)

            name = name or module
        if not callable(loader):
            raise TypeError("Lazy dependencies require a module name or loader")
        self.loader, self.name, self.pending = loader, name, None

    async def load(self):
        if self.pending is None:

            async def run():
                try:
                    return await invoke(self.loader)
                except Exception as error:
                    self.pending = None
                    raise DependencyLoadError(self.name or "Lazy dependency") from error

            self.pending = asyncio.create_task(run())
            self.pending.add_done_callback(
                lambda t: None if t.cancelled() else t.exception()
            )
        return await asyncio.shield(self.pending)

    preload = load


def lazy(loader, name=None):
    return LazyDependency(loader, name)


class TemplateCache:
    def __init__(self):
        self.values = {}
        self.pending = {}
        self.generation = 0

    def clear(self):
        self.generation += 1
        self.values.clear()
        self.pending.clear()

    def clean(self):
        expired = [
            key
            for key, (expires, _) in self.values.items()
            if expires <= time.monotonic()
        ]
        for key in expired:
            del self.values[key]
        return len(expired)

    async def get(self, key, duration, factory):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Cache key must be a nonempty string")
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("Cache duration must be finite and nonnegative")
        if duration == 0:
            return await invoke(factory)
        self.clean()
        if key in self.values:
            return self.values[key][1]
        if key not in self.pending:
            generation = self.generation

            async def load():
                try:
                    result = await invoke(factory)
                    if generation == self.generation:
                        self.values[key] = (time.monotonic() + duration, result)
                    return result
                finally:
                    if self.pending.get(key) is asyncio.current_task():
                        self.pending.pop(key, None)

            task = asyncio.create_task(load())
            task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
            self.pending[key] = task
        return await asyncio.shield(self.pending[key])
