"""Synthetic framework workload, intentionally independent of the notes UI."""

import asyncio
import json
from time import perf_counter

from js import document, window
from pyscript.ffi import is_none
from list_fixture import ListWorkload, ListCell
from patera.desktop.ui import (
    Application,
    Component,
    page,
    react,
    react_factory,
    tag,
    template,
)


@tag("bench-child")
class Child(Component):
    def markup(self):
        return template('<button @click="noop">child</button>')

    def noop(self, event):
        pass


@page("/")
@tag("bench-workload")
class Workload(Component):
    count = react(0)
    outer = react(0)
    rows = react_factory(lambda: list(range(50)))

    def markup(self):
        return template("""
        <h1>Framework fixture</h1>
        <button id="single" @click="exercise" :action='"single"'>single</button>
        <button id="scheduled" @click="exercise" :action='"scheduled"'>scheduled</button>
        <button id="burst" @click="exercise" :action='"burst"'>burst</button>
        <button id="nested" @click="exercise" :action='"nested"'>nested</button>
        <button id="unchanged" @click="exercise" :action='"unchanged"'>unchanged</button>
        <button id="list" @click="exercise" :action='"list"'>list</button>
        <button id="soak" @click="exercise" :action='"soak"'>soak</button>
        <button id="race" @click="exercise" :action='"race"'>race</button>
        <button id="shutdown" @click="exercise" :action='"shutdown"'>shutdown</button>
        <button id="legacy" @click="exercise" :action='"legacy"'>legacy text</button>
        <div data-bind="outer"><span id="count" data-bind="count">{{ component.count }}</span></div>
        <div data-bind="rows">{% for row in component.rows %}<button @click="noop">{{ row }}</button>{% endfor %}</div>
        <div id="children"></div>
        <div data-ui-text="label"><button @click="noop">obsolete listener</button></div>
        <form id="form" @submit="noop"><button type="submit">submit</button></form>
        <button id="modified" @click="noop" data-ui-prevent-default data-ui-stop-propagation>modifier</button>
        <input id="stable-input" value="keep selection">
        {% for item in range(1000) %}<button class="stable" @click="noop">{{ item }}</button>{% endfor %}
        """)

    async def mounted(self):
        self.element.setAttribute("data-ready", "true")

    def noop(self, event):
        pass

    async def exercise(self, event, args):
        action = args["action"]
        self.app.diagnostics.reset()
        start = perf_counter()
        if action in {"single", "scheduled"}:
            self.count += 1
        elif action == "burst":
            for _ in range(100):
                self.count += 1
        elif action == "nested":
            self.outer += 1
            self.count += 1
        elif action == "unchanged":
            self.invalidate("outer")
        elif action == "list":
            self.rows = [*reversed(self.rows), len(self.rows)]
        elif action == "legacy":
            self.state["label"] = "replacement"
        elif action == "soak":
            for _ in range(100):
                await self.insert_html(
                    "<bench-child></bench-child>", target=self.select("#children")
                )
                self.select("bench-child").remove()
                await asyncio.sleep(0)
        elif action == "race":
            # The event task must survive removal of the initiating page.
            async def navigate():
                for _ in range(10):
                    task = asyncio.create_task(self.app.navigate("/slow"))
                    await asyncio.sleep(0.01)
                    await self.app.navigate("/")
                    await asyncio.gather(task, return_exceptions=True)
                await asyncio.sleep(0.15)
                publish(self.app, action, start, None)

            self.app.adapter.spawn(navigate())
            return
        elif action == "shutdown":

            async def stop():
                await self.app.stop()
                await self.app.stop()
                publish(self.app, action, start, None)

            self.app.adapter.spawn(stop())
            return
        if hasattr(self.app.adapter, "updates") and action != "scheduled":
            await self.app.flush()
        await self.app.adapter.wait_children(self)
        await asyncio.sleep(0)
        publish(self.app, action, start, self.count)


@page("/slow")
@tag("bench-slow")
class Slow(Component):
    async def markup(self):
        await asyncio.sleep(0.1)
        return template("<h1>Stale route</h1>")


def publish(application, action, start, value):
    result = document.getElementById("benchmark-result")
    if is_none(result):
        result = document.createElement("pre")
        result.id = "benchmark-result"
        document.body.appendChild(result)
    snapshot = application.diagnostics.snapshot()
    if application.adapter is None or hasattr(application.adapter, "resources"):
        snapshot = application.diagnostics_snapshot()
    result.textContent = json.dumps(
        dict(
            action=action,
            elapsed_ms=(perf_counter() - start) * 1000,
            value=value,
            diagnostics=snapshot,
        )
    )


app = Application(
    pages=[Workload, Slow, ListWorkload],
    components=[Child, ListCell],
    batch_updates="batch=1" in str(window.location.search),
    diagnostics=True,
)
