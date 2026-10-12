"""
AI interface tests. The embedding libraries (the "augmentation" extra) are not
needed: the package imports them only when an augmentation provider starts.
"""

from __future__ import annotations

import json
import sys
from typing import Any, AsyncIterator, Optional

import httpx
import pytest
from sqlalchemy import Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from patera import Request, Response
from patera.controller import Controller, get, path, post

# Skip (instead of failing collection) when patera-aiinterface is not installed.
pytest.importorskip("patera.aiinterface")

from patera.aiinterface import (  # noqa: E402
    AiService,
    AiServiceConfig,
    AugmentationConfig,
    BaseHistoryProvider,
    BaseServiceProvider,
    ChatMessage,
    ChatResponse,
    SqlHistoryProvider,
    augmentation,
    history,
    system_prompt,
    user_prompt,
)
from patera.aiinterface.augmentation_provider import BaseAugmentationProvider  # noqa: E402
from patera.aiinterface.augmentation_provider import (  # noqa: E402
    base_augmentation_provider as augmentation_module,
)
from patera.aiinterface.service_provider import ollama as ollama_module  # noqa: E402
from patera.aiinterface.service_provider import openai as openai_module  # noqa: E402
from patera.database.sql import (  # noqa: E402
    DeclarativeBaseModel,
    SqlDatabase,
    SqlDatabaseConfig,
    SqlDatabaseManager,
    transactional,
)
from patera.injectable import Inject  # noqa: E402

pytestmark = pytest.mark.integration

CONFIG = AiServiceConfig(BASE_URL="http://llm.local", MODEL="m", API_KEY="key")


def _answer(content: str) -> ChatResponse:
    return ChatResponse(
        provider="fake",
        model="m",
        message=ChatMessage(role="assistant", content=content),
    )


class FakeProvider(BaseServiceProvider):
    """Answers with a numbered reply and records the messages it was sent."""

    def __init__(self, fail: bool = False, rewrite_to: str = "standalone question"):
        self.sent: list[list[tuple[str, str]]] = []
        self.configs: list[AiServiceConfig] = []
        self.fail = fail
        self.rewrite_to = rewrite_to

    def _record(self, messages: list[ChatMessage]) -> int:
        self.sent.append([(m.role, m.content) for m in messages])
        if self.fail:
            raise RuntimeError("model unavailable")
        return len(self.sent)

    async def complete(self, messages, configs) -> ChatResponse:
        self.configs.append(configs)
        number = self._record(messages)
        if messages[0].content.startswith("Rewrite the user's follow-up question"):
            return _answer(self.rewrite_to)
        return _answer(f"answer {number}")

    async def stream(self, messages, configs):
        number = self._record(messages)
        for part in ("part ", str(number)):
            yield _answer(part)


class MemoryHistory(BaseHistoryProvider):
    def __init__(self):
        self.sessions: dict[Any, list[ChatMessage]] = {}
        self.limits: list[Optional[int]] = []

    async def load(self, session_id, limit):
        self.limits.append(limit)
        messages = self.sessions.get(session_id, [])
        return list(messages[-limit:] if limit else messages)

    async def append(self, session_id, messages):
        self.sessions.setdefault(session_id, []).extend(messages)

    async def new_session_id(self):
        return f"s{len(self.sessions) + 1}"


class FakeAugmentation(BaseAugmentationProvider):
    def __init__(self, texts):
        super().__init__()
        self.texts = texts
        self.queries: list[str] = []

    def bind(self, configs, ext):
        super().bind(configs, ext)
        self.configs_seen = configs

    def load_embedding_model(self):
        raise AssertionError("FakeAugmentation never embeds")

    async def relevant_texts(self, query, req=None):
        self.queries.append(query)
        return list(self.texts)


# ---- plain calls --------------------------------------------------------------


class Assistant(AiService):
    service_provider = FakeProvider()

    @system_prompt("You translate to <:language>.")
    @user_prompt("Translate <:text>")
    async def translate(self, text: str, language: str = "German") -> ChatResponse: ...

    @system_prompt("Stream")
    @user_prompt("About <:topic>")
    async def story(self, topic: str) -> AsyncIterator[ChatResponse]: ...


def _service(make_app, cls, **configs):
    name = (
        "".join("_" + c if c.isupper() else c for c in cls.__name__).lstrip("_").upper()
    )
    app = make_app(**{name: CONFIG.model_copy(update=configs)})
    return cls(app)


async def test_the_prompt_goes_straight_to_the_model(make_app):
    service = _service(make_app, Assistant)
    service.service_provider = FakeProvider()
    response = await service.translate("hello", "French")
    assert response.message.content == "answer 1"
    assert response.session_id is None
    assert service.service_provider.sent[0] == [
        ("system", "You translate to French."),
        ("user", "Translate hello"),
    ]
    # Keyword arguments and defaults fill the placeholders too.
    await service.translate(text="bye")
    assert service.service_provider.sent[1][-1] == ("user", "Translate bye")
    assert service.service_provider.sent[1][0] == ("system", "You translate to German.")


async def test_streaming_methods_are_iterated_without_await(make_app):
    service = _service(make_app, Assistant)
    service.service_provider = FakeProvider()
    parts = [chunk.message.content async for chunk in service.story("cats")]
    assert parts == ["part ", "1"]
    assert service.service_provider.sent[0][-1] == ("user", "About cats")


@path("/ai")
class AiController(Controller):
    assistant: Inject[Assistant]

    @get("/translate/<text>")
    async def translate(self, req: Request, text: str) -> Response:
        answer = await self.assistant.translate(text, "Slovenian")
        parts = [c.message.content async for c in self.assistant.story(text)]
        return req.res.json({"answer": answer.message.content, "parts": parts})


async def test_calls_inside_a_request(make_app, client_for):
    Assistant.service_provider = FakeProvider()
    app = make_app(controllers=[AiController], ASSISTANT=CONFIG)
    async with client_for(app) as client:
        res = await client.get("/ai/translate/hello")
    assert res.json() == {"answer": "answer 1", "parts": ["part ", "2"]}


# ---- history --------------------------------------------------------------------


class ChatAssistant(AiService):
    service_provider = FakeProvider()
    history_provider = MemoryHistory()

    @history
    @system_prompt("Be brief.")
    @user_prompt("<:message>")
    async def chat(self, session_id: Optional[str], message: str) -> ChatResponse: ...

    @history
    @system_prompt("Be brief.")
    @user_prompt("<:message>")
    async def chat_stream(
        self, session_id: Optional[str], message: str
    ) -> AsyncIterator[ChatResponse]: ...


def _chat_service(make_app, **configs) -> ChatAssistant:
    ChatAssistant.service_provider = FakeProvider()
    ChatAssistant.history_provider = MemoryHistory()
    return _service(make_app, ChatAssistant, **configs)


async def test_history_continues_a_session(make_app):
    service = _chat_service(make_app)
    first = await service.chat(None, "Hi")
    assert first.session_id == "s1"

    second = await service.chat(first.session_id, "And now?")
    assert second.session_id == "s1"
    assert service.service_provider.sent[1] == [
        ("system", "Be brief."),
        ("user", "Hi"),
        ("assistant", "answer 1"),
        ("user", "And now?"),
    ]
    # The system prompt is sent every time but never stored.
    stored = service.history_provider.sessions["s1"]
    assert [(m.role, m.content) for m in stored] == [
        ("user", "Hi"),
        ("assistant", "answer 1"),
        ("user", "And now?"),
        ("assistant", "answer 2"),
    ]


async def test_the_current_system_prompt_is_used_for_old_sessions(make_app):
    service = _chat_service(make_app)
    first = await service.chat(None, "Hi")
    original = ChatAssistant.chat.__wrapped__  # the decorated method
    original.__system_prompt__ = "Be detailed."  # e.g. changed in a new release
    try:
        await service.chat(first.session_id, "More")
    finally:
        original.__system_prompt__ = "Be brief."
    assert service.service_provider.sent[1][0] == ("system", "Be detailed.")


async def test_history_limit(make_app):
    service = _chat_service(make_app, HISTORY_LIMIT=2)
    session = (await service.chat(None, "one")).session_id
    await service.chat(session, "two")
    await service.chat(session, "three")
    assert service.history_provider.limits == [2, 2]
    assert service.service_provider.sent[2] == [
        ("system", "Be brief."),
        ("user", "two"),
        ("assistant", "answer 2"),
        ("user", "three"),
    ]
    assert len(service.history_provider.sessions[session]) == 6

    unlimited = _chat_service(make_app, HISTORY_LIMIT=None)
    session = (await unlimited.chat(None, "one")).session_id
    await unlimited.chat(session, "two")
    assert unlimited.history_provider.limits == [None]


async def test_streamed_answers_are_saved_when_the_stream_ends(make_app):
    service = _chat_service(make_app)
    chunks = [c async for c in service.chat_stream(None, "Tell me")]
    assert {c.session_id for c in chunks} == {"s1"}
    stored = service.history_provider.sessions["s1"]
    assert [(m.role, m.content) for m in stored] == [
        ("user", "Tell me"),
        ("assistant", "part 1"),
    ]


async def test_failed_calls_save_nothing(make_app):
    service = _chat_service(make_app)
    service.service_provider = FakeProvider(fail=True)
    with pytest.raises(RuntimeError, match="model unavailable"):
        await service.chat(None, "Hi")
    assert service.history_provider.sessions == {}


def test_history_methods_need_a_session_id_parameter():
    with pytest.raises(TypeError, match="session_id"):

        class Broken(AiService):
            service_provider = FakeProvider()

            @history
            @user_prompt("<:message>")
            async def chat(self, message: str) -> ChatResponse: ...


class NoHistoryProvider(AiService):
    service_provider = FakeProvider()

    @history
    @user_prompt("<:message>")
    async def chat(self, session_id: Optional[str], message: str) -> ChatResponse: ...


def test_missing_history_provider_fails_at_startup(make_app):
    with pytest.raises(TypeError, match="history_provider"):
        _service(make_app, NoHistoryProvider)


# ---- augmentation -------------------------------------------------------------


class Researcher(AiService):
    service_provider = FakeProvider()
    history_provider = MemoryHistory()
    augmentation_provider = FakeAugmentation(["Doc A", "Doc B"])

    @history
    @augmentation
    @system_prompt("Answer from the documents.")
    @user_prompt("<:question>")
    async def ask(self, session_id: Optional[str], question: str) -> ChatResponse: ...


CONTEXT = (
    "Documents that may help with the next message. Use them when they are "
    "relevant and ignore them otherwise.\n\n[1] Doc A\n\n[2] Doc B"
)


def _researcher(make_app, texts=("Doc A", "Doc B"), **augmentation):
    Researcher.service_provider = FakeProvider()
    Researcher.history_provider = MemoryHistory()
    Researcher.augmentation_provider = FakeAugmentation(list(texts))
    configs = (
        {"AUGMENTATION": AugmentationConfig(**augmentation)} if augmentation else {}
    )
    return _service(make_app, Researcher, **configs)


async def test_documents_go_in_a_context_message(make_app):
    service = _researcher(make_app)
    first = await service.ask(None, "What is Patera?")
    assert service.service_provider.sent[0] == [
        ("system", "Answer from the documents."),
        ("system", CONTEXT),
        ("user", "What is Patera?"),
    ]
    assert service.augmentation_provider.queries == ["What is Patera?"]

    # The history keeps the conversation, not the documents.
    await service.ask(first.session_id, "Who wrote it?")
    assert service.service_provider.sent[1] == [
        ("system", "Answer from the documents."),
        ("user", "What is Patera?"),
        ("assistant", "answer 1"),
        ("system", CONTEXT),
        ("user", "Who wrote it?"),
    ]
    stored = service.history_provider.sessions[first.session_id]
    assert [m.role for m in stored] == ["user", "assistant", "user", "assistant"]


async def test_augmentation_without_matches_adds_no_context(make_app):
    service = _researcher(make_app, texts=())
    await service.ask(None, "Q")
    assert service.service_provider.sent[0] == [
        ("system", "Answer from the documents."),
        ("user", "Q"),
    ]


async def test_context_template_can_be_changed(make_app):
    service = _researcher(make_app, CONTEXT_TEMPLATE="Facts:\n<:documents>")
    await service.ask(None, "Q")
    assert service.service_provider.sent[0][1] == (
        "system",
        "Facts:\n[1] Doc A\n\n[2] Doc B",
    )


async def test_follow_up_questions_are_rewritten_before_searching(make_app):
    service = _researcher(make_app, REWRITE_QUERY=True)
    first = await service.ask(None, "Tell me about Patera.")
    # No history yet: no rewrite, the question is searched as it is.
    assert len(service.service_provider.sent) == 1
    assert service.augmentation_provider.queries == ["Tell me about Patera."]

    await service.ask(first.session_id, "Who wrote it?")
    rewrite_call, answer_call = service.service_provider.sent[1:]
    assert rewrite_call[0][0] == "system"
    assert rewrite_call[1] == (
        "user",
        "Conversation:\nuser: Tell me about Patera.\nassistant: answer 1\n\n"
        "Follow-up question: Who wrote it?",
    )
    # The rewritten question is only used for the search.
    assert service.augmentation_provider.queries[-1] == "standalone question"
    assert answer_call[-1] == ("user", "Who wrote it?")
    rewrite_configs = service.service_provider.configs[1]
    assert (
        rewrite_configs.RESPONSE_FORMAT is None and rewrite_configs.TEMPERATURE == 0.0
    )


async def test_an_empty_rewrite_falls_back_to_the_question(make_app):
    service = _researcher(make_app, REWRITE_QUERY=True)
    service.service_provider.rewrite_to = "   "
    first = await service.ask(None, "One")
    await service.ask(first.session_id, "Two")
    assert service.augmentation_provider.queries[-1] == "Two"


async def test_questions_are_not_rewritten_by_default(make_app):
    service = _researcher(make_app)
    first = await service.ask(None, "One")
    await service.ask(first.session_id, "Two")
    assert len(service.service_provider.sent) == 2
    assert service.augmentation_provider.queries == ["One", "Two"]


def test_default_history_limit_is_ten():
    assert AiServiceConfig(BASE_URL="http://x", MODEL="m").HISTORY_LIMIT == 10


def test_augmentation_settings_default_when_not_configured(make_app):
    service = _service(make_app, Researcher)
    assert service.augmentation_provider.configs_seen == AugmentationConfig()


class NoAugmentationProvider(AiService):
    service_provider = FakeProvider()

    @augmentation
    @user_prompt("<:q>")
    async def ask(self, q: str) -> ChatResponse: ...


def test_missing_augmentation_provider_fails_at_startup(make_app):
    with pytest.raises(TypeError, match="augmentation_provider"):
        _service(make_app, NoAugmentationProvider)


def test_embedding_libraries_are_not_imported():
    assert "sentence_transformers" not in sys.modules
    assert "torch" not in sys.modules


def test_missing_augmentation_extra_names_the_extra(make_app):
    import importlib.util

    if importlib.util.find_spec("sentence_transformers") is not None:
        pytest.skip("the augmentation extra is installed")

    class Holder:
        app = make_app()

    with pytest.raises(ImportError, match=r"patera-aiinterface\[augmentation\]"):
        BaseAugmentationProvider().bind(AugmentationConfig(), Holder())


def test_rank_orders_by_cosine_similarity_and_applies_the_limits():
    pytest.importorskip("numpy")

    class Doc:
        def __init__(self, text, vector):
            self.text = text
            self.vector = vector

    docs = [
        Doc("orthogonal", [0.0, 1.0]),
        Doc("close", [0.9, 0.1]),
        Doc("exact", [2.0, 0.0]),
        Doc("near", [0.8, 0.3]),
        Doc("zero", [0.0, 0.0]),
    ]
    provider = BaseAugmentationProvider()
    provider._configs = AugmentationConfig(MINIMAL_SIMILARITY=0.9, MATCH_LIMIT=2)
    assert [d.text for d in provider.rank([1.0, 0.0], docs)] == ["exact", "close"]
    provider._configs = AugmentationConfig(MINIMAL_SIMILARITY=0.995, MATCH_LIMIT=5)
    assert [d.text for d in provider.rank([1.0, 0.0], docs)] == ["exact"]
    assert provider.rank([1.0, 0.0], []) == []
    assert augmentation_module.MISSING_EXTRA.startswith("Retrieval augmentation")


# ---- SQL history (SQLite) -----------------------------------------------------------


class ChatBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "chats"


class ChatRow(ChatBase):
    __tablename__ = "ai_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    order_number: Mapped[int] = mapped_column(Integer)


class ChatDb(SqlDatabase):
    __db_name__ = "chats"


class ChatDatabases(SqlDatabaseManager):
    databases = [ChatDb]


class ChatHistory(SqlHistoryProvider[ChatRow]):
    model = ChatRow


class SqlChat(AiService):
    service_provider = FakeProvider()
    history_provider = ChatHistory()

    @history
    @system_prompt("Be brief.")
    @user_prompt("<:message>")
    async def chat(self, session_id: Optional[str], message: str) -> ChatResponse: ...

    @history
    @system_prompt("Be brief.")
    @user_prompt("<:message>")
    async def chat_stream(
        self, session_id: Optional[str], message: str
    ) -> AsyncIterator[ChatResponse]: ...


@path("/chat")
class SqlChatController(Controller):
    chat: Inject[SqlChat]

    @get("/<session>/<message>")
    async def send(self, req: Request, session: str, message: str) -> Response:
        answer = await self.chat.chat(None if session == "new" else session, message)
        return req.res.json(
            {"session_id": answer.session_id, "answer": answer.message.content}
        )


@path("/tx")
class TransactionalChatController(Controller):
    chat: Inject[SqlChat]

    @post("/<message>")
    @transactional
    async def send(self, req: Request, message: str) -> Response:
        session = ChatRow.get_session()  # the request's session of the "chats" database
        session.add(
            ChatRow(session_id="handler", role="note", content=message, order_number=0)
        )
        await session.flush()  # the handler now holds SQLite's write lock
        answer = await self.chat.chat(None, message)
        again = await self.chat.chat(
            answer.session_id, "and again"
        )  # sees the first call
        if message == "fail":
            raise RuntimeError("the handler fails after chatting")
        return req.res.json({"session_id": again.session_id})

    @post("/stream/<message>")
    @transactional
    async def stream(self, req: Request, message: str) -> Response:
        # The body is sent after the handler returns, when the request's
        # transaction is already committed and closed.
        async def body():
            async for chunk in self.chat.chat_stream(None, message):
                yield f"{chunk.session_id}|{chunk.message.content}\n"

        return req.res.stream_text(body())


@pytest.fixture
async def sql_app(make_app, tmp_path):
    SqlChat.service_provider = FakeProvider()
    app = make_app(
        controllers=[SqlChatController, TransactionalChatController],
        extensions=[ChatDatabases],
        CHAT_DB=SqlDatabaseConfig(
            DATABASE_URI=f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}"
        ),
        SQL_CHAT=CONFIG.model_copy(update={"HISTORY_LIMIT": 3}),
        DEBUG=False,
    )
    db = app.get_extension(ChatDatabases).get_database("chats")
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(ChatBase.metadata.create_all, tables=[ChatRow.__table__])
    yield app
    await db.disconnect()


async def _rows(app) -> list[tuple]:
    db = app.get_extension(ChatDatabases).get_database("chats")
    async with db.session_scope() as session:
        rows = (await session.execute(select(ChatRow).order_by(ChatRow.id))).scalars()
        return [(r.session_id, r.order_number, r.role, r.content) for r in rows]


async def test_sql_history_outside_a_request(sql_app):
    service = SqlChat(sql_app)
    first = await service.chat(None, "Hi")
    await service.chat(first.session_id, "Again")
    await service.chat(first.session_id, "Third")

    sid = first.session_id
    assert len(sid) == 36  # a UUID string by default
    assert await _rows(sql_app) == [
        (sid, 0, "user", "Hi"),
        (sid, 1, "assistant", "answer 1"),
        (sid, 2, "user", "Again"),
        (sid, 3, "assistant", "answer 2"),
        (sid, 4, "user", "Third"),
        (sid, 5, "assistant", "answer 3"),
    ]
    # HISTORY_LIMIT=3: the last three stored messages, oldest first
    assert service.service_provider.sent[2] == [
        ("system", "Be brief."),
        ("assistant", "answer 1"),
        ("user", "Again"),
        ("assistant", "answer 2"),
        ("user", "Third"),
    ]


async def test_sql_history_in_requests_needs_no_commit(sql_app, client_for):
    async with client_for(sql_app) as client:
        first = (await client.get("/chat/new/Hello")).json()
        second = (await client.get(f"/chat/{first['session_id']}/More")).json()
    assert second["session_id"] == first["session_id"]
    rows = await _rows(sql_app)
    assert [(r[1], r[2], r[3]) for r in rows] == [
        (0, "user", "Hello"),
        (1, "assistant", "answer 1"),
        (2, "user", "More"),
        (3, "assistant", "answer 2"),
    ]


# ---- service providers (HTTP mocked) ------------------------------------------------


def _mock_httpx(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


MESSAGES = [
    ChatMessage(role="system", content="sys"),
    ChatMessage(role="user", content="Hello"),
]


async def test_openai_complete(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "m",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hi!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            },
        )

    _mock_httpx(monkeypatch, handler)
    configs = CONFIG.model_copy(
        update={
            "ORGANIZATION_ID": "org-1",
            "PROJECT_ID": "proj-1",
            "TEMPERATURE": None,
            "RESPONSE_FORMAT": {"type": "json_object"},
        }
    )
    response = await openai_module.OpenAIServiceProvider().complete(MESSAGES, configs)
    assert response.message.content == "Hi!"
    assert response.usage.total_tokens == 5
    sent = requests[0]
    payload = json.loads(sent.content)
    assert str(sent.url) == "http://llm.local/chat/completions"
    assert sent.headers["authorization"] == "Bearer key"
    assert sent.headers["openai-organization"] == "org-1"
    assert sent.headers["openai-project"] == "proj-1"
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Hello"},
    ]
    assert payload["response_format"] == {"type": "json_object"}
    assert "temperature" not in payload

    requests.clear()
    await openai_module.OpenAIServiceProvider().complete(MESSAGES, CONFIG)
    payload = json.loads(requests[0].content)
    assert "response_format" not in payload and payload["temperature"] == 0.0
    assert "openai-organization" not in requests[0].headers


async def test_openai_requires_an_api_key():
    with pytest.raises(ValueError, match="API_KEY"):
        await openai_module.OpenAIServiceProvider().complete(
            MESSAGES, CONFIG.model_copy(update={"API_KEY": None})
        )


async def test_openai_stream(monkeypatch):
    chunks = [
        {"model": "m", "choices": [{"delta": {"role": "assistant", "content": "He"}}]},
        {
            "model": "m",
            "choices": [{"delta": {"content": "llo"}, "finish_reason": "stop"}],
        },
    ]

    def handler(request):
        assert json.loads(request.content)["stream_options"] == {"include_usage": True}
        body = (
            "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    _mock_httpx(monkeypatch, handler)
    provider = openai_module.OpenAIServiceProvider()
    parts = [c.message.content async for c in provider.stream(MESSAGES, CONFIG)]
    assert "".join(parts) == "Hello"


async def test_ollama_complete_and_stream(monkeypatch):
    payloads = []

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        if payload["stream"]:
            lines = [
                {"model": "m", "message": {"role": "assistant", "content": "A"}},
                {
                    "model": "m",
                    "message": {"role": "assistant", "content": "B"},
                    "done": True,
                },
            ]
            return httpx.Response(
                200, text="\n".join(json.dumps(line) for line in lines)
            )
        return httpx.Response(
            200,
            json={
                "model": "m",
                "message": {"role": "assistant", "content": "ok"},
                "done": True,
            },
        )

    _mock_httpx(monkeypatch, handler)
    provider = ollama_module.OllamaServiceProvider()
    response = await provider.complete(MESSAGES, CONFIG)
    assert response.message.content == "ok" and response.finish_reason == "stop"
    assert payloads[0]["options"] == {"temperature": 0.0}
    parts = [c.message.content async for c in provider.stream(MESSAGES, CONFIG)]
    assert "".join(parts) == "AB"


@pytest.mark.parametrize(
    ("response_format", "expected"),
    [
        ({"type": "json_object"}, "json"),
        (
            {
                "type": "json_schema",
                "json_schema": {"name": "x", "schema": {"type": "object"}},
            },
            {"type": "object"},
        ),
    ],
)
async def test_ollama_response_format(monkeypatch, response_format, expected):
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200, json={"model": "m", "message": {"role": "assistant", "content": "{}"}}
        )

    _mock_httpx(monkeypatch, handler)
    configs = CONFIG.model_copy(update={"RESPONSE_FORMAT": response_format})
    await ollama_module.OllamaServiceProvider().complete(MESSAGES, configs)
    assert payloads[0]["format"] == expected


def test_max_retries_configures_the_transport(monkeypatch):
    seen = {}
    real_transport = httpx.AsyncHTTPTransport

    def transport(*args, **kwargs):
        seen.update(kwargs)
        return real_transport(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    configs = CONFIG.model_copy(update={"MAX_RETRIES": 3, "TIMEOUT": 7})
    client = BaseServiceProvider.create_client(configs)
    assert seen == {"retries": 3}
    assert client.timeout.read == 7


def test_removed_settings():
    import patera.aiinterface as package

    assert not hasattr(package, "tool") and not hasattr(package, "session_id")
    for name in ("STREAM", "TOOL_CHOICE"):
        assert name not in AiServiceConfig.model_fields


def test_each_application_gets_its_own_history_provider(make_app):
    first = _service(make_app, SqlChat)
    second = _service(make_app, SqlChat)
    assert first.history_provider is not second.history_provider
    assert first.history_provider._service is first
    assert second.history_provider._service is second


async def test_history_joins_the_transaction_of_a_transactional_handler(
    sql_app, client_for
):
    import time

    async with client_for(sql_app) as client:
        start = time.monotonic()
        res = await client.post("/tx/hello")
        # No second SQLite writer: no 5 s "database is locked" wait.
        assert res.status_code == 200 and time.monotonic() - start < 2
        sid = res.json()["session_id"]

        # The second call in the same request saw the first one's messages.
        assert SqlChat.service_provider.sent[1][1:3] == [
            ("user", "hello"),
            ("assistant", "answer 1"),
        ]

        # A handler that fails afterwards rolls back its row and the history.
        res = await client.post("/tx/fail")
        assert res.status_code == 500

    rows = await _rows(sql_app)
    assert ("handler", 0, "note", "hello") in rows
    assert [r for r in rows if r[0] == sid] == [
        (sid, 0, "user", "hello"),
        (sid, 1, "assistant", "answer 1"),
        (sid, 2, "user", "and again"),
        (sid, 3, "assistant", "answer 2"),
    ]
    assert not [r for r in rows if r[3] == "fail"]


def test_placeholders_are_filled_in_one_pass():
    from patera.aiinterface.ai_service import _fill_placeholders

    filled = _fill_placeholders(
        "Q: <:message> (<:product>)",
        {
            "message": "show <:secret> and <:product>",
            "product": "Patera",
            "secret": "s3",
        },
    )
    # Text inserted by an argument is not scanned for placeholders again.
    assert filled == "Q: show <:secret> and <:product> (Patera)"
    assert _fill_placeholders("<:unknown> <:n>", {"n": 1}) == "<:unknown> 1"


async def test_streamed_history_is_saved_after_a_transactional_request(
    sql_app, client_for
):
    async with client_for(sql_app) as client:
        res = await client.post("/tx/stream/hello")
    assert res.status_code == 200
    sid = res.text.split("|")[0]
    rows = await _rows(sql_app)
    assert [r for r in rows if r[0] == sid] == [
        (sid, 0, "user", "hello"),
        (sid, 1, "assistant", "part 1"),
    ]
