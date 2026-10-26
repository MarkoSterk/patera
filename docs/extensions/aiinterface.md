# AI interface

!!! warning "Experimental"

    This package is not yet ready for production use; its API may change in any release.

`patera-aiinterface` connects to chat completion APIs (OpenAI-compatible and Ollama), with
prompts, chat history and retrieval augmentation.

```sh
uv add "patera[aiinterface]"
pip install "patera-aiinterface[augmentation]"   # retrieval: sentence-transformers, PyTorch, pgvector
```

Retrieval augmentation needs the `augmentation` extra; everything else works without it.

## A service

```python
from typing import AsyncIterator, Optional

from patera.aiinterface import (
    AiService, AiServiceConfig, ChatResponse, SqlHistoryProvider, history, system_prompt, user_prompt,
)
from patera.aiinterface.service_provider.openai import OpenAIServiceProvider


class ChatHistory(SqlHistoryProvider[ChatMessageRow]):   # a model with session_id, role,
    model = ChatMessageRow                               # content and order_number columns


class Assistant(AiService):
    service_provider = OpenAIServiceProvider()           # or OllamaServiceProvider()
    history_provider = ChatHistory()

    @system_prompt("You are a helpful translator.")
    @user_prompt("Translate '<:text>' to <:language>.")
    async def translate(self, text: str, language: str = "German") -> ChatResponse: ...

    @history
    @system_prompt("You are a friendly assistant.")
    @user_prompt("<:message>")
    async def chat(self, session_id: Optional[str], message: str) -> AsyncIterator[ChatResponse]: ...


class Config(BaseConfig):
    ...
    ASSISTANT: AiServiceConfig = AiServiceConfig(
        BASE_URL="https://api.openai.com/v1", API_KEY="...", MODEL="gpt-4o-mini", HISTORY_LIMIT=10,
    )
```

```python
answer = await self.assistant.translate("Good morning", "French")
async for chunk in self.assistant.chat(None, "Hi!"):      # None starts a new session
    session_id = chunk.session_id                         # send it back to continue the chat
```

Every call builds the messages the same way: the current system prompt first, then (with
`@history`) the session's last `HISTORY_LIMIT` messages, then the user prompt with its `<:name>`
placeholders filled from the method's arguments. A method annotated
`-> AsyncIterator[ChatResponse]` streams and is iterated directly, without `await`; the others
return one `ChatResponse`.

## History

`@history` needs a `history_provider` and a `session_id` parameter on the method.

- `None` starts a new session (a random UUID by default; override `new_session_id()`), and every
  response carries the session id.
- The question and the answer are saved after the call (a streamed answer once the stream ends);
  nothing is saved when the call fails.
- The system prompt is never stored, so a changed prompt applies to existing sessions too.
- In a `@transactional` handler, `SqlHistoryProvider` uses the request's session, so the messages
  commit or roll back with the request. Anywhere else it uses a short transaction of its own, so
  it works in plain requests, CLI commands and scheduled jobs.
- Writes to one chat session never overlap, also across worker processes: each write first locks
  the chat session until it commits (an advisory lock on PostgreSQL, the database's write lock on
  SQLite). Other databases take turns within a process.
- Implement `load()` and `append()` of `BaseHistoryProvider` for other storage.

Enforce ownership of conversation and session identifiers in your application.

### Summaries

`HISTORY_SUMMARY = HistorySummaryConfig(EVERY=10, MAX_WORDS=250)` keeps a rolling summary of long
conversations. Each call sends the summary, then the messages it does not cover. Once `EVERY`
messages beyond the latest `HISTORY_LIMIT` are uncovered, they are merged into the summary by one
extra model call in the background, after the answer is returned. The summary is a row of the
messages table (`role="summary"`), every message stays stored in full, and concurrent updates
never overwrite each other. `await service.update_summary(session_id)` runs an update by hand.
Custom history providers support it by implementing `load_since`, `load_summary` and
`save_summary`.

## Retrieval augmentation

`@augmentation` adds the most similar documents as a context message just before the user message
(`CONTEXT_TEMPLATE`, with `<:documents>`); the history never stores them. With history and
`REWRITE_QUERY=True`, a follow-up such as "who wrote it?" is first rewritten by the model into a
standalone question for the search (one extra call per message; off by default).

The documents are rows with a text and a `VectorColumn` (pgvector's type):

```python
from patera.aiinterface.augmentation_provider import BaseAugmentationProvider
from patera.aiinterface.augmentation_provider.embeddings import VectorColumn


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    vector = mapped_column(VectorColumn(384))     # the embedding model's dimension


class Documents(BaseAugmentationProvider[Document]):
    model = Document

    def base_query(self, req):                    # optional: limit the candidates
        return select(Document).where(Document.owner_id == req.user.id)


class Assistant(AiService):
    ...
    augmentation_provider = Documents()
```

- The embedding model is loaded the first time a text is embedded (in a worker thread), not when
  the application starts, so CLI commands never load it. Override `load_embedding_model()` to use
  another model.
- `await assistant.augmentation_provider.add_documents(texts, **columns)` embeds and stores
  documents with the same model that embeds the questions.
- On PostgreSQL with the pgvector extension the search is one query ordered by cosine distance;
  on other databases the candidates are compared in Python (`RETRIEVAL` forces either).
- Settings: `AiServiceConfig.AUGMENTATION = AugmentationConfig(MATCH_LIMIT=5, MINIMAL_SIMILARITY=0.9, ...)`.

A missing provider for `@history` or `@augmentation` fails when the service starts.

## Other settings

`RESPONSE_FORMAT` (for example `{"type": "json_object"}`), `TEMPERATURE` (`None` for the
provider's default), `MAX_RETRIES` (failed connections), `ORGANIZATION_ID` and `PROJECT_ID`
(OpenAI headers).

!!! warning "Safety"

    Use fake providers in tests. Keep untrusted retrieved text separate from application
    instructions, bound history and retrieval work, handle provider errors and stream
    cancellation, and never let generated text authorize application actions.

A complete example lives in
[`examples/ai_chat`](https://github.com/MarkoSterk/Patera/tree/main/examples/ai_chat).
