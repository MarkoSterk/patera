from datetime import timezone
from typing import Any

from pydantic import BaseModel, Field

from patera import HttpStatus, MediaType, Request, Response, abort
from patera.controller import (
    Controller,
    consumes,
    delete,
    get,
    path,
    post,
    produces,
    put,
)
from patera.database.sql import transactional
from patera.injectable import Inject

from app import App
from app.database import Note, NoteRepository


class NoteIn(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=200_000)


def note_json(note: Note) -> dict[str, Any]:
    updated = note.updated_at
    if updated.tzinfo is None:  # SQLite returns naive datetimes; they are UTC
        updated = updated.replace(tzinfo=timezone.utc)
    return {
        "id": note.id,
        "title": note.title,
        "body": note.body,
        "updated_at": updated.isoformat(),
    }


@path("/api/notes")
class NotesApi(Controller[App]):
    """
    The window's page talks to this JSON API like any web page would. JSON
    bodies also keep other websites out: a page elsewhere cannot send JSON to
    this server without a CORS preflight, which it does not allow.
    """

    notes: Inject[NoteRepository]

    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def list_notes(self, req: Request) -> Response:
        """The notes, most recently changed first; ?q= searches titles and text."""
        query = self.notes.query.order_by(Note.updated_at.desc(), Note.id.desc())
        text = str(req.query_parameters.get("q", "")).strip()
        if text:
            query = query.where(
                Note.title.icontains(text, autoescape=True)
                | Note.body.icontains(text, autoescape=True)
            )
        return req.res.json([note_json(note) for note in await query.all()])

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON, HttpStatus.CREATED)
    @transactional
    async def create(self, req: Request, data: NoteIn) -> Response:
        note = await self.notes.create_and_flush(title=data.title, body=data.body)
        return req.res.json(note_json(note)).status(HttpStatus.CREATED)

    @put("/<int:note_id>")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @transactional
    async def update(self, req: Request, note_id: int, data: NoteIn) -> Response:
        note = await self._note(note_id)
        note.title = data.title
        note.body = data.body
        await self.notes.save(note)
        return req.res.json(note_json(note))

    @delete("/<int:note_id>")
    @transactional
    async def remove(self, req: Request, note_id: int) -> Response:
        await self.notes.delete(await self._note(note_id))
        return req.res.no_content()

    async def _note(self, note_id: int) -> Note:
        note = await self.notes.get(note_id)
        if note is None:
            abort("There is no such note.", HttpStatus.NOT_FOUND)
        return note
