"""A native SQLite API; the browser never imports this module."""

import sqlite3

from pydantic import BaseModel, Field

from patera import MediaType, Request, abort
from patera.controller import Controller, consumes, get, path, post, put
from patera.desktop import user_data_dir


class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=100_000)


@path("/api/notes")
class NotesAPI(Controller):
    def connect(self):
        connection = sqlite3.connect(user_data_dir(self.app.app_name) / "notes.sqlite")
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL)"
        )
        return connection

    @get("/")
    async def index(self, req: Request):
        connection = self.connect()
        try:
            notes = [
                dict(row)
                for row in connection.execute("SELECT * FROM notes ORDER BY id DESC")
            ]
            return req.res.json(notes)
        finally:
            connection.close()

    @get("/<int:note_id>")
    async def detail(self, req: Request, note_id: int):
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            if row is None:
                abort("Note not found", 404)
            return req.res.json(dict(row))
        finally:
            connection.close()

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    async def create(self, req: Request, data: NoteInput):
        connection = self.connect()
        try:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO notes(title, body) VALUES (?, ?)",
                    (data.title, data.body),
                )
            return req.res.json({"id": cursor.lastrowid, **data.model_dump()}).status(
                201
            )
        finally:
            connection.close()

    @put("/<int:note_id>")
    @consumes(MediaType.APPLICATION_JSON)
    async def update(self, req: Request, note_id: int, data: NoteInput):
        connection = self.connect()
        try:
            with connection:
                cursor = connection.execute(
                    "UPDATE notes SET title = ?, body = ? WHERE id = ?",
                    (data.title, data.body, note_id),
                )
                if not cursor.rowcount:
                    abort("Note not found", 404)
            return req.res.json({"id": note_id, **data.model_dump()})
        finally:
            connection.close()
