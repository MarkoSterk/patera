"""Ordered hooks and cancellable lifetimes, independent of the DOM."""

from __future__ import annotations

import asyncio
import inspect
from enum import Enum


class Lifecycle(str, Enum):
    EXTENSION_INIT = "extension-init"
    BEFORE_INIT = "before-init"
    BEFORE_INIT_RESOLVE = "before-init-resolve"
    AFTER_INIT = "after-init"
    BEFORE_RERENDER = "before-rerender"
    AFTER_RERENDER = "after-rerender"
    AFTER_DISCONNECT = "after-disconnect"


def lifecycle(*stages: Lifecycle):
    if not stages or any(not isinstance(stage, Lifecycle) for stage in stages):
        raise ValueError("Provide at least one Lifecycle stage")

    def decorate(method):
        method.__ui_lifecycle__ = tuple(dict.fromkeys(stages))
        return method

    return decorate


def effective_methods(instance):
    """Base-first declaration order; any subclass override suppresses its base."""
    owners = {}
    for cls in type(instance).__mro__:
        for name in vars(cls):
            owners.setdefault(name, cls)
    for cls in reversed(type(instance).__mro__):
        for name, value in vars(cls).items():
            if owners[name] is cls and inspect.isfunction(value):
                yield name, getattr(instance, name)


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


async def run_hooks(instance, stage, scope=None):
    for _, method in effective_methods(instance):
        if stage in getattr(method, "__ui_lifecycle__", ()):
            if scope:
                await scope.wait(invoke(method))
            else:
                await invoke(method)


class ElementDisconnectedError(asyncio.CancelledError):
    """Expected end of a component's lifetime, never an application error."""


class Scope:
    def __init__(self, on_error=None, *, diagnostics=None):
        self.closed = False
        self.tasks = set()
        self.cleanups = []
        self.on_error = on_error
        self._closed = asyncio.Event()
        self.diagnostics = diagnostics

    def check(self):
        if self.closed:
            raise ElementDisconnectedError()

    def spawn(self, awaitable):
        if self.closed:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            self.check()
        task = asyncio.create_task(awaitable)
        if self.diagnostics:
            self.diagnostics.track_task(task)
        self.tasks.add(task)

        def completed(done):
            self.tasks.discard(done)
            if not done.cancelled() and (error := done.exception()) is not None:
                if not self.closed and self.on_error:
                    self.on_error(error)

        task.add_done_callback(completed)
        return task

    async def wait(self, awaitable, *, shared=False):
        if self.closed:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            self.check()
        task = asyncio.ensure_future(awaitable)
        if self.diagnostics:
            self.diagnostics.track_task(task)
        closed = asyncio.create_task(self._closed.wait())
        # Always retrieve late failures, including cancellation-resistant work.
        task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        try:
            await asyncio.wait((task, closed), return_when=asyncio.FIRST_COMPLETED)
            self.check()
            return task.result()
        finally:
            closed.cancel()
            if not shared and not task.done():
                task.cancel()

    def cancel(self):
        if self.closed:
            return
        self.closed = True
        self._closed.set()
        for task in tuple(self.tasks):
            if task is not asyncio.current_task():
                task.cancel()

    async def close(self):
        self.cancel()
        callbacks, self.cleanups = self.cleanups, []
        for callback in reversed(callbacks):
            try:
                await invoke(callback)
            except Exception as error:
                if self.on_error:
                    self.on_error(error)
