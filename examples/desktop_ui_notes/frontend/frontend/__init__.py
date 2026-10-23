from patera.desktop.ui import Application
from .layouts.main import MainLayout


class NotesApplication(Application):
    """Shared workspace data. Mutations update mounted views without a reload."""

    async def refresh_notes(self):
        self.set_data("notes", await self.api.get_json("/api/notes/"))

    def remember_note(self, note):
        self.set_data(
            "notes",
            sorted(
                [item for item in self.get_data("notes") if item["id"] != note["id"]]
                + [note],
                key=lambda item: item["id"],
                reverse=True,
            ),
        )

    def toggle_favorite(self, note_id):
        favorites = set(self.get_data("favorites"))
        if note_id in favorites:
            favorites.remove(note_id)
        else:
            favorites.add(note_id)
        self.set_data("favorites", sorted(favorites))


app = NotesApplication(
    __name__,
    base_layout=MainLayout,
    data={
        "notes": [],
        "favorites": [],
        "drafts": {},
        "preferences": {"theme": "light", "density": "comfortable"},
        "notice": "All notes are stored on this device.",
    },
)
