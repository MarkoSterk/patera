from typing import TYPE_CHECKING, Optional

from app.assistant import Assistant
from pydantic import BaseModel, Field

from patera import MediaType, Request, Response
from patera.controller import Controller, consumes, get, path, post, produces
from patera.injectable import Inject
from patera.serializers import ndjson_line

if TYPE_CHECKING:
    from app import App  # noqa: F401 - used in quoted generic bases


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = None  # leave out to start a new chat


@path("/api/chat")
class ChatApi(Controller["App"]):
    assistant: Inject[Assistant]

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def chat(self, req: Request, body: ChatIn) -> Response:
        """Answers in one response."""
        answer = await self.assistant.chat(body.session_id, body.message)
        return req.res.json(
            {"session_id": answer.session_id, "answer": answer.message.content}
        )

    @post("/stream")
    @consumes(MediaType.APPLICATION_JSON)
    async def stream(self, req: Request, body: ChatIn) -> Response:
        """Streams the answer as NDJSON lines: {"session_id": ..., "text": ...}."""

        async def lines():
            async for chunk in self.assistant.chat_stream(
                body.session_id, body.message
            ):
                if chunk.message.content:
                    yield ndjson_line(
                        {"session_id": chunk.session_id, "text": chunk.message.content}
                    )

        return req.res.stream_text(
            lines(), media_type=MediaType.APPLICATION_X_NDJSON.value
        )

    @get("/<session_id>")
    @produces(MediaType.APPLICATION_JSON)
    async def messages(self, req: Request, session_id: str) -> Response:
        """The messages of a chat session, oldest first, and its current summary."""
        history = self.assistant.history_provider
        stored = await history.load(session_id, None)
        summary = await history.load_summary(session_id)
        return req.res.json(
            {
                "summary": summary.text if summary else None,
                "messages": [{"role": m.role, "content": m.content} for m in stored],
            }
        )
