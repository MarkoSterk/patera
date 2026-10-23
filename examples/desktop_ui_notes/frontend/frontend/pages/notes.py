from __future__ import annotations
from typing import TYPE_CHECKING
from patera.desktop.ui import (
    Component,
    Lifecycle,
    SubLayout,
    lifecycle,
    page,
    query_param,
    tag,
    template,
)
from ..layouts.note import NoteLayout

if TYPE_CHECKING:
    from patera.desktop.ui.types import Event, SubmitEvent


@page("/", title="Python Notes")
@tag("notes-home")
class NotesHome(Component):
    search = query_param("filter", "")

    @property
    def visible_notes(self):
        return [
            note
            for note in self.app.get_data("notes", [])
            if self.search.lower() in note["title"].lower()
        ]

    @lifecycle(Lifecycle.BEFORE_INIT)
    async def load(self):
        self.app.set_data("notes", await self.api.get_json("/api/notes/"))

    def markup(self):
        return template(name="templates/home.html")

    def filter_notes(self, event: Event) -> None:
        self.search = str(event.target.value)


@page(
    "/notes/<int:note_id>",
    title=lambda page: page.note["title"],
    sublayouts=[SubLayout(NoteLayout)],
    target="#note-content",
)
@tag("note-detail")
class NoteDetail(Component):
    @lifecycle(Lifecycle.BEFORE_INIT)
    async def load(self):
        self.note = await self.api.get_json(
            f"/api/notes/{self.context.params['note_id']}"
        )

    def markup(self):
        return template(name="templates/detail.html", note=self.note)


@page(
    "/notes/<int:note_id>/edit",
    title="Edit note",
    sublayouts=[SubLayout(NoteLayout)],
    target="#note-content",
)
@tag("note-edit")
class EditNote(Component):
    @lifecycle(Lifecycle.BEFORE_INIT)
    async def load(self):
        self.note = await self.api.get_json(
            f"/api/notes/{self.context.params['note_id']}"
        )

    def markup(self):
        return template(name="templates/edit.html", note=self.note)

    async def save(self, event: SubmitEvent) -> None:
        await self.api.put_json(
            f"/api/notes/{self.note['id']}",
            {
                "title": str(self.select('[name="title"]').value),
                "body": str(self.select('[name="body"]').value),
            },
        )
        await self.app.navigate(f"/notes/{self.note['id']}")
