"""Key identity, child lifetime, and bounded virtual rendering fixture."""

import asyncio
from time import perf_counter

from patera.desktop.ui import Component, page, react, react_factory, tag, template


@tag("bench-list-cell")
class ListCell(Component):
    count = react(0)

    def markup(self):
        if not getattr(self, "seen", False):
            self.seen = True
            self.app.list_mounts += 1
        return template(
            '<button @click="increment"><span data-bind="count">{{component.count}}</span></button><small>{{args.label}}</small>'
        )

    def increment(self, event):
        self.count += 1

    async def unmounted(self):
        if getattr(self, "seen", False):
            self.app.list_unmounts += 1


@page("/lists")
@tag("bench-list-workload")
class ListWorkload(Component):
    deferred_label = react("initial", binding="deferred")
    items = react_factory(lambda: [dict(id=i, title=f"Row {i}") for i in range(20)])
    large = react_factory(
        lambda: [dict(id=i, title=f"Virtual {i}") for i in range(5000)]
    )

    def markup(self):
        self.app.list_mounts = 0
        self.app.list_unmounts = 0
        self.app.list_events = []
        return template("""<h1>List fixture</h1>
          {% for action in ['reverse', 'modify', 'prepend', 'remove', 'filter', 'refill', 'clear', 'snapshot', 'labels', 'deferred'] %}
          <button id="{{action}}" @click="exercise" :action='{{action|tojson}}'>{{action}}</button>
          {% endfor %}
          <div id="keyed">{% keyed "items" %}{% for row in component.items %}
            <article data-ui-key="{{row.id}}">
              <input class="edit" value="{{row.title}}">
              <b data-bind="labels">{{row.title}}</b>
              <button class="row-action" @click="{{'alternate' if row.get('changed') else 'original'}}" :item="{{row.id}}">action</button>
              <bench-list-cell :label='{{row.title|tojson}}'></bench-list-cell>
            </article>
          {% endfor %}{% endkeyed %}</div>
          <div id="virtual">{% virtual "large", component.large, row_height=20, height=200, overscan=2 %}
            <span class="virtual-label" data-bind="vlabels">{{item.title}}</span>
            <bench-list-cell :label='{{item.title|tojson}}'></bench-list-cell>
          {% endvirtual %}</div>
          <div id="deferred-list">{% keyed "deferred" %}{% if component.deferred_label is not none %}
            <bench-list-cell data-ui-key="deferred" defer :label='{{component.deferred_label|tojson}}'></bench-list-cell>
          {% endif %}{% endkeyed %}</div>
        """)

    async def mounted(self):
        self.element.setAttribute("data-ready", "true")

    def original(self, event, args):
        self.app.list_events.append(["original", args["item"]])

    def alternate(self, event, args):
        self.app.list_events.append(["alternate", args["item"]])

    async def exercise(self, event, args):
        from fixture import publish

        action = args["action"]
        self.app.diagnostics.reset()
        start = perf_counter()
        if action == "reverse":
            self.items = list(reversed(self.items))
        elif action == "modify":
            self.items = [
                {**row, "title": "Updated", "changed": True} if row["id"] == 0 else row
                for row in self.items
            ]
        elif action == "prepend":
            self.items = [dict(id=100, title="Added"), *self.items]
        elif action == "remove":
            self.items = [row for row in self.items if row["id"] != 100]
        elif action == "filter":
            self.large = self.large[:3]
        elif action == "refill":
            self.large = [dict(id=i, title=f"Virtual {i}") for i in range(5000)]
        elif action == "labels":
            self.invalidate("labels")
            self.invalidate("vlabels")
        elif action == "deferred":
            self.deferred_label = "changed"
        elif action == "clear":
            self.items = []
            self.large = []
            self.deferred_label = None
        await self.flush()
        await self.wait_children()
        await asyncio.sleep(0)
        publish(
            self.app,
            action,
            start,
            dict(
                mounts=self.app.list_mounts,
                unmounts=self.app.list_unmounts,
                events=self.app.list_events,
            ),
        )
