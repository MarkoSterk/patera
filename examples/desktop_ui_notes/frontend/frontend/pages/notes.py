from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from patera.desktop.ui import (
    Component,
    Lifecycle,
    SubLayout,
    lifecycle,
    page,
    query_param,
    react,
    tag,
    template,
)
from ..layouts.note import NoteLayout

if TYPE_CHECKING:
    from patera.desktop.ui.types import InputEvent, MouseEvent, Event


@page("/", title="Python Notes · Overview")
@tag("notes-home")
class NotesHome(Component):
    loading_samples = react(False)

    @property
    def word_count(self):
        return sum(len(note["body"].split()) for note in self.app.get_data("notes"))

    def markup(self):
        return template(name="templates/home.html")

    async def add_samples(self, event: MouseEvent):
        if self.loading_samples:
            return
        self.loading_samples = True
        samples = [
            (
                "Welcome to your workspace",
                "A place for ideas, plans, and everyday notes.\n\nOpen the library, choose a note, and switch between reading and editing. The note browser stays in place.\n\nTry starring this note, or start a draft and leave the editor. Your draft will still be here when you return during this session.",
            ),
            (
                "Weekend field notes",
                "Saturday\nWalk the riverside trail. Bring a camera and a notebook.\n\nSunday\nVisit the farmers market. Pick up fresh herbs and something for lunch.\n\nRemember: leave room for a detour.",
            ),
            (
                "Project launch checklist",
                "Before launch\n• Review onboarding\n• Check keyboard navigation\n• Test a fresh offline installation\n• Write release notes\n\nAfter launch\nCollect feedback and choose the next small improvement.",
            ),
            (
                "Reading list",
                "Books to explore\n• A collection of short stories\n• A guide to urban gardening\n• An illustrated history of maps\n\nKeep a sentence from each book that changes how you see something.",
            ),
            (
                "Ideas for a quieter desk",
                "Keep only the current notebook on the desk.\nGive cables a home.\nMove reference material to a shelf.\nAdd a small plant near the window.\n\nStart with one corner, not the whole room.",
            ),
            (
                "Meeting · next steps",
                "Decisions\nKeep the first release focused on the essential workflow.\n\nNext steps\nAlex: prepare the draft.\nSam: collect examples.\nMe: review navigation and empty states.\n\nFollow up next Thursday.",
            ),
        ]
        try:
            for title, body in samples:
                note = await self.api.post_json(
                    "/api/notes/", {"title": title, "body": body}
                )
                self.app.remember_note(note)
            self.app.set_data("notice", "Six example notes added. Make them your own.")
        finally:
            self.loading_samples = False


class NoteCollection(Component, ABC):
    search = query_param("filter", "")
    sort = query_param("sort", "newest")
    favorites_only = False

    @property
    def visible_notes(self):
        favorites = self.app.get_data("favorites")
        notes = [
            note
            for note in self.app.get_data("notes")
            if self.search.casefold() in (note["title"] + " " + note["body"]).casefold()
            and (not self.favorites_only or note["id"] in favorites)
        ]
        if self.sort == "title":
            return sorted(notes, key=lambda note: note["title"].casefold())
        return sorted(notes, key=lambda note: note["id"], reverse=self.sort != "oldest")

    @abstractmethod
    def markup(self):
        return template(name="templates/library.html")

    def filter_notes(self, event: InputEvent):
        self.app.update_query_parameters(
            {"filter": str(event.target.value) or None}, history="replace"
        )

    def sort_notes(self, event: Event):
        self.sort = str(event.target.value)


@page("/library", title="Library · Python Notes")
@tag("notes-library")
class Library(NoteCollection):
    def markup(self):
        return super().markup()


@page("/favorites", title="Favorites · Python Notes")
@tag("notes-favorites")
class Favorites(NoteCollection):
    favorites_only = True

    def markup(self):
        return super().markup()


@page("/new", title="New note · Python Notes")
@tag("new-note")
class NewNote(Component):
    def markup(self):
        return template("""<div class="page-heading"><div><p class="eyebrow">CAPTURE AN IDEA</p>
        <h1>New note</h1><p class="muted">Your draft stays here while you explore the workspace.</p></div></div>
        <section class="panel editor-panel"><note-form></note-form></section>""")


class LoadNote(Component, ABC):
    @lifecycle(Lifecycle.BEFORE_INIT)
    async def load(self):
        note_id = self.context.params["note_id"]
        self.note = next(
            (note for note in self.app.get_data("notes") if note["id"] == note_id), None
        )
        if self.note is None:
            self.note = await self.api.get_json(f"/api/notes/{note_id}")
            self.app.remember_note(self.note)

    @abstractmethod
    def markup(self):
        pass


@page(
    "/notes/<int:note_id>",
    title=lambda page: page.note["title"],
    sublayouts=[SubLayout(NoteLayout)],
    target="#note-content",
)
@tag("note-detail")
class NoteDetail(LoadNote):
    confirm_delete = react(False)

    def markup(self):
        return template(name="templates/detail.html", note=self.note)

    def favorite(self, event: MouseEvent):
        self.app.toggle_favorite(self.note["id"])

    def ask_delete(self, event: MouseEvent):
        self.confirm_delete = not self.confirm_delete

    async def delete_note(self, event: MouseEvent):
        await self.api.delete(f"/api/notes/{self.note['id']}")
        self.app.set_data(
            "notes",
            [
                note
                for note in self.app.get_data("notes")
                if note["id"] != self.note["id"]
            ],
        )
        self.app.set_data(
            "favorites",
            [key for key in self.app.get_data("favorites") if key != self.note["id"]],
        )
        drafts = dict(self.app.get_data("drafts"))
        drafts.pop(str(self.note["id"]), None)
        self.app.set_data("drafts", drafts)
        self.app.set_data("notice", "Note deleted from this device.")
        await self.app.navigate("/library")


@page(
    "/notes/<int:note_id>/edit",
    title="Edit note",
    sublayouts=[SubLayout(NoteLayout)],
    target="#note-content",
)
@tag("note-edit")
class EditNote(LoadNote):
    def markup(self):
        return template(name="templates/edit.html", note=self.note)


@page("/settings", title="Preferences · Python Notes")
@tag("notes-settings")
class Settings(Component):
    def markup(self):
        return template(name="templates/settings.html")

    async def change(self, event: Event):
        preferences = dict(self.app.get_data("preferences"))
        preferences[str(event.target.name)] = str(event.target.value)
        self.app.set_data("preferences", preferences)
        await self.app.emit("preferences-changed")
        self.app.set_data("notice", "Workspace appearance updated for this session.")
