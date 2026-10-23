from __future__ import annotations

from typing import TYPE_CHECKING

from patera.desktop.ui import Component, State, event, template, tag

if TYPE_CHECKING:
    from patera.desktop.ui.types import SubmitEvent


@tag("note-form")
class NoteForm(Component):
    def __init__(self, app, element):
        super().__init__(app, element)
        self.state = State(message="")

    def markup(self):
        return template("""<form @submit="save">
          <label>Title <input name="title" required maxlength="200"></label>
          <label>Note <textarea name="body" rows="5"></textarea></label>
          <button>Save note</button><p data-bind="message" role="status">{{ component.state["message"] }}</p>
        </form>""")

    @event("submit")
    async def save(self, event: SubmitEvent) -> None:
        event.preventDefault()
        title = self.element.querySelector('[name="title"]').value
        body = self.element.querySelector('[name="body"]').value
        self.state["message"] = "Saving…"
        note = await self.api.post_json("/api/notes/", {"title": title, "body": body})
        await self.app.navigate(f"/notes/{note['id']}")
