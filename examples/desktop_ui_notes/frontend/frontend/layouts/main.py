from __future__ import annotations
from typing import TYPE_CHECKING
from patera.desktop.ui import (
    Component,
    Lifecycle,
    layout,
    lifecycle,
    react,
    tag,
    template,
)

if TYPE_CHECKING:
    from patera.desktop.ui.types import MouseEvent


@layout
@tag("notes-layout")
class MainLayout(Component):
    current = react("/")
    visits = react(0)

    @lifecycle(Lifecycle.BEFORE_INIT)
    async def load(self):
        await self.app.refresh_notes()
        self.on_cleanup(self.app.on("route-finished", self.navigated))
        self.on_cleanup(self.app.on("preferences-changed", self.apply_preferences))
        self.apply_preferences()

    def navigated(self, context):
        self.current = context.url.split("?", 1)[0]
        self.visits += 1

    def apply_preferences(self):
        for key, value in self.app.get_data("preferences").items():
            self.element.setAttribute("data-" + key, value)

    def markup(self):
        return template(name="templates/layout.html")

    async def refresh(self, event: MouseEvent) -> None:
        await self.app.refresh_notes()
        self.app.set_data("notice", "Library refreshed from this device.")
