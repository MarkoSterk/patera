from __future__ import annotations
from typing import TYPE_CHECKING
from patera.desktop.ui import Component, Lifecycle, lifecycle, react, template, tag

if TYPE_CHECKING:
    from patera.desktop.ui.types import SubmitEvent, InputEvent, MouseEvent


@tag("note-form")
class NoteForm(Component):
    message = react("")
    word_count = react(0)

    @lifecycle(Lifecycle.BEFORE_INIT)
    def load(self):
        self.note_id = self.args.get("note_id")
        self.key = str(self.note_id) if self.note_id else "new"
        self.original = next(
            (note for note in self.app.get_data("notes") if note["id"] == self.note_id),
            {"title": "", "body": ""},
        )
        self.values = self.app.get_data("drafts").get(self.key, self.original)
        self.word_count = len(self.values["body"].split())
        self.saving = False

    def markup(self):
        return template(name="templates/form.html")

    def changed(self, event: InputEvent):
        self.values = {
            "title": str(self.select('[name="title"]').value),
            "body": str(self.select('[name="body"]').value),
        }
        drafts = dict(self.app.get_data("drafts"))
        drafts[self.key] = self.values
        self.app.set_data("drafts", drafts)
        self.word_count = len(self.values["body"].split())
        self.message = "Draft kept for this session."

    def clear_draft(self):
        drafts = dict(self.app.get_data("drafts"))
        drafts.pop(self.key, None)
        self.app.set_data("drafts", drafts)

    async def discard(self, event: MouseEvent):
        self.clear_draft()
        self.values = self.original
        self.word_count = len(self.values["body"].split())
        self.message = "Draft discarded."
        await self.rerender()

    async def save(self, event: SubmitEvent):
        if self.saving:
            return
        self.changed(event)
        if not self.values["title"].strip():
            self.message = "Give your note a title before saving."
            return
        self.saving = True
        button = self.select('button[type="submit"]')
        button.disabled = True
        self.message = "Saving…"
        try:
            payload = {**self.values, "title": self.values["title"].strip()}
            note = (
                await self.api.put_json(f"/api/notes/{self.note_id}", payload)
                if self.note_id
                else await self.api.post_json("/api/notes/", payload)
            )
            self.app.remember_note(note)
            self.clear_draft()
            self.app.set_data("notice", "Note saved on this device.")
            await self.app.navigate(f"/notes/{note['id']}")
        except Exception:
            self.message = "Could not save. Your draft is still here; please try again."
        finally:
            self.saving = False
            if not self.scope.closed:
                button.disabled = False
