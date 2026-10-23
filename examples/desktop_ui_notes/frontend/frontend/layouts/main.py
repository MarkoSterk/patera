from __future__ import annotations
from typing import TYPE_CHECKING
from patera.desktop.ui import Component, layout, react, tag, template

if TYPE_CHECKING:
    from patera.desktop.ui.types import MouseEvent


@layout
@tag("notes-layout")
class MainLayout(Component):
    visits = react(0)

    def markup(self):
        return template(name="templates/layout.html")

    def increment(self, event: MouseEvent) -> None:
        self.visits += 1
