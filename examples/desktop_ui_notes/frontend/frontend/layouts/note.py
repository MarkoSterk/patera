from __future__ import annotations
from typing import TYPE_CHECKING
from patera.desktop.ui import Component, layout, react, tag, template

if TYPE_CHECKING:
    from patera.desktop.ui.types import InputEvent


@layout
@tag("note-layout")
class NoteLayout(Component):
    search = react("")

    @property
    def visible_notes(self):
        return [
            note
            for note in self.app.get_data("notes")
            if self.search.casefold() in note["title"].casefold()
        ]

    def filter_notes(self, event: InputEvent):
        self.search = str(event.target.value)

    def markup(self):
        return template(name="templates/note_layout.html")
