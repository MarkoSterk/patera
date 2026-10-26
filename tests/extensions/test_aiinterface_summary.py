"""
Rolling history summaries (AiServiceConfig.HISTORY_SUMMARY), stored as rows of
the messages table. Runs on SQLite and, with PATERA_TEST_PG_URI, PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import AsyncIterator, Optional

import pytest
from pydantic import ValidationError
from sqlalchemy import Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

pytest.importorskip("patera.aiinterface")

from patera.aiinterface import (  # noqa: E402
    AiService,
    AiServiceConfig,
    AugmentationConfig,
    BaseServiceProvider,
    ChatMessage,
    ChatResponse,
    HistorySummary,
    HistorySummaryConfig,
    SqlHistoryProvider,
    augmentation,
    history,
    system_prompt,
    user_prompt,
)
from patera.database.sql import (  # noqa: E402
    DeclarativeBaseModel,
    SqlDatabase,
    SqlDatabaseConfig,
    SqlDatabaseManager,
)
from patera.utilities import wait_for_background_tasks  # noqa: E402

from tests.extensions.test_aiinterface import (  # noqa: E402
    CONFIG,
    FakeAugmentation,
    MemoryHistory,
)

pytestmark = pytest.mark.integration


def _answer(content: str) -> ChatResponse:
    return ChatResponse(
        provider="fake",
        model="m",
        message=ChatMessage(role="assistant", content=content),
    )


class SummarizingProvider(BaseServiceProvider):
    """
    Answers chat calls with "answer N". Summary calls get "S<k>[...]" listing
    the user messages they were given (and the previous summary), so tests can
    see exactly what was merged.
    """

    def __init__(self):
        self.calls: list[list[tuple[str, str]]] = []
        self.summary_calls = 0
        self.fail_summaries = False
        self.summary_delay = 0.0

    async def complete(self, messages, configs) -> ChatResponse:
        self.calls.append([(m.role, m.content) for m in messages])
        if messages[0].content.startswith("You maintain the summary"):
            self.summary_calls += 1
            await asyncio.sleep(self.summary_delay)
            if self.fail_summaries:
                raise RuntimeError("summary model unavailable")
            request = messages[1].content
            previous = request.split("\n")[1]
            users = re.findall(r"^user: (.*)$", request, re.M)
            merged = ([previous] if previous != "(none yet)" else []) + users
            return _answer(f"S{self.summary_calls}[{', '.join(merged)}]")
        if messages[0].content.startswith("Rewrite the user's follow-up"):
            return _answer("standalone question")
        return _answer(f"answer {len(self.calls)}")

    async def stream(self, messages, configs):
        response = await self.complete(messages, configs)
        for part in response.message.content.split(" "):
            yield _answer(part + " ")

    def chat_calls(self):
        return [
            c
            for c in self.calls
            if not c[0][1].startswith(
                ("You maintain the summary", "Rewrite the user's")
            )
        ]


class SumBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "summaries"


class SumRow(SumBase):
    __tablename__ = "ai_summary_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    order_number: Mapped[int] = mapped_column(Integer)


class SumDb(SqlDatabase):
    __db_name__ = "summaries"


class SumDatabases(SqlDatabaseManager):
    databases = [SumDb]


class SumHistory(SqlHistoryProvider[SumRow]):
    model = SumRow


class Chat(AiService):
    service_provider = SummarizingProvider()
    history_provider = SumHistory()
    augmentation_provider = FakeAugmentation(["Doc"])

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

    @history
    @augmentation
    @system_prompt("Be brief.")
    @user_prompt("<:message>")
    async def research(
        self, session_id: Optional[str], message: str
    ) -> ChatResponse: ...


BACKENDS = ["sqlite"] + (["postgresql"] if os.environ.get("PATERA_TEST_PG_URI") else [])
SUMMARY = HistorySummaryConfig(EVERY=2)


@pytest.fixture(params=BACKENDS)
async def chat(request, make_app, tmp_path):
    if request.param == "sqlite":
        uri = f"sqlite+aiosqlite:///{tmp_path / 'summaries.db'}"
    else:
        uri = os.environ["PATERA_TEST_PG_URI"]
    Chat.service_provider = SummarizingProvider()
    Chat.augmentation_provider = FakeAugmentation(["Doc"])
    app = make_app(
        extensions=[SumDatabases],
        SUM_DB=SqlDatabaseConfig(DATABASE_URI=uri),
        CHAT=CONFIG.model_copy(
            update={
                "HISTORY_LIMIT": 2,
                "HISTORY_SUMMARY": SUMMARY,
                "AUGMENTATION": AugmentationConfig(REWRITE_QUERY=True),
            }
        ),
    )
    db = app.get_extension(SumDatabases).get_database("summaries")
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(SumBase.metadata.drop_all, tables=[SumRow.__table__])
        await conn.run_sync(SumBase.metadata.create_all, tables=[SumRow.__table__])
    yield Chat(app)
    # As the application's shutdown does: let background summaries finish first.
    await wait_for_background_tasks(None)
    async with db.engine.begin() as conn:
        await conn.run_sync(SumBase.metadata.drop_all, tables=[SumRow.__table__])
    await db.disconnect()


async def _rows(service) -> list[tuple]:
    db = service.app.get_extension(SumDatabases).get_database("summaries")
    async with db.session_scope() as session:
        rows = (await session.execute(select(SumRow).order_by(SumRow.id))).scalars()
        return [(r.order_number, r.role, r.content) for r in rows]


async def _say(service, session_id, message, stream=False):
    if stream:
        chunks = [c async for c in service.chat_stream(session_id, message)]
        session_id = chunks[0].session_id
    else:
        session_id = (await service.chat(session_id, message)).session_id
    await wait_for_background_tasks(None)  # let the summary update finish
    return session_id


async def test_older_messages_are_replaced_by_a_rolling_summary(chat):
    provider = chat.service_provider
    sid = await _say(chat, None, "one")
    assert provider.summary_calls == 0  # 2 messages: nothing beyond the limit yet

    await _say(chat, sid, "two", stream=True)
    # 4 stored messages, HISTORY_LIMIT=2: the oldest two (EVERY=2) were merged.
    assert provider.summary_calls == 1
    assert await chat.history_provider.load_summary(sid) == HistorySummary("S1[one]", 1)

    await _say(chat, sid, "three")
    assert provider.chat_calls()[2] == [
        ("system", "Be brief."),
        ("system", "Summary of the earlier conversation:\nS1[one]"),
        ("user", "two"),
        ("assistant", "answer 2 "),
        ("user", "three"),
    ]
    # The summary is merged further: the previous one plus the next two messages.
    assert await chat.history_provider.load_summary(sid) == HistorySummary(
        "S2[S1[one], two]", 3
    )

    rows = await _rows(chat)
    summaries = [r for r in rows if r[1] == "summary"]
    assert summaries == [
        (3, "summary", "S2[S1[one], two]")
    ]  # one row, updated in place
    # Every message is still stored in full, in order.
    messages = [r for r in rows if r[1] != "summary"]
    assert [(r[0], r[1]) for r in messages] == [
        (0, "user"),
        (1, "assistant"),
        (2, "user"),
        (3, "assistant"),
        (4, "user"),
        (5, "assistant"),
    ]
    # load() (used to show a conversation) never returns the summary row.
    assert [m.content for m in await chat.history_provider.load(sid, None)][0] == "one"
    assert len(await chat.history_provider.load(sid, None)) == 6


async def test_without_summaries_at_most_limit_plus_every_messages_are_sent(chat):
    provider = chat.service_provider
    provider.fail_summaries = True  # every summary call fails (and is logged)
    sid = await _say(chat, None, "m1")
    for number in range(2, 6):
        await _say(chat, sid, f"m{number}")
    assert await chat.history_provider.load_summary(sid) is None
    last = provider.chat_calls()[-1]
    # HISTORY_LIMIT (2) + EVERY (2) earlier messages, then the question.
    assert len(last) == 1 + 4 + 1
    assert last[-1] == ("user", "m5")
    assert len(await chat.history_provider.load(sid, None)) == 10


async def test_a_stale_summary_is_never_saved(chat):
    sid = await _say(chat, None, "one")
    history_provider = chat.history_provider
    assert (
        await history_provider.save_summary(sid, HistorySummary("A", 1), None) is True
    )
    # Someone else saved "A" first: an update based on "no summary" is refused.
    assert (
        await history_provider.save_summary(sid, HistorySummary("B", 1), None) is False
    )
    current = await history_provider.load_summary(sid)
    assert current == HistorySummary("A", 1)
    assert (
        await history_provider.save_summary(sid, HistorySummary("C", 3), current)
        is True
    )
    assert await history_provider.load_summary(sid) == HistorySummary("C", 3)


async def test_one_summary_update_at_a_time_per_session(chat):
    provider = chat.service_provider
    sid = await _say(chat, None, "one")
    provider.summary_delay = 0.05
    await chat.chat(sid, "two")  # schedules an update in the background
    results = await asyncio.gather(chat.update_summary(sid), chat.update_summary(sid))
    await wait_for_background_tasks(None)
    assert provider.summary_calls == 1
    assert results.count(True) <= 1


async def test_the_question_rewrite_sees_the_summary(chat):
    sid = await _say(chat, None, "one")
    await _say(chat, sid, "two")
    await chat.research(sid, "and then?")
    rewrite = [c for c in chat.service_provider.calls if c[0][1].startswith("Rewrite")][
        -1
    ]
    assert rewrite[1][1].startswith(
        "Conversation:\n(summary of the earlier part) S1[one]\n"
    )


def test_summaries_need_a_history_limit():
    with pytest.raises(ValidationError, match="HISTORY_LIMIT"):
        AiServiceConfig(
            BASE_URL="x", MODEL="m", HISTORY_LIMIT=None, HISTORY_SUMMARY=SUMMARY
        )


class MemoryChat(AiService):
    service_provider = SummarizingProvider()
    history_provider = MemoryHistory()

    @history
    @user_prompt("<:message>")
    async def chat(self, session_id: Optional[str], message: str) -> ChatResponse: ...


def test_summaries_need_a_provider_that_stores_them(make_app):
    assert MemoryHistory().supports_summaries is False
    assert SumHistory().supports_summaries is True
    app = make_app(MEMORY_CHAT=CONFIG.model_copy(update={"HISTORY_SUMMARY": SUMMARY}))
    with pytest.raises(TypeError, match="does not store summaries"):
        MemoryChat(app)


from patera import Request, Response  # noqa: E402
from patera.controller import Controller, path, post  # noqa: E402
from patera.database.sql import transactional  # noqa: E402
from patera.injectable import Inject  # noqa: E402


@path("/chat")
class TransactionalChat(Controller):
    chat: Inject[Chat]

    @post("/<session>/<message>")
    @transactional
    async def send(self, req: Request, session: str, message: str) -> Response:
        answer = await self.chat.chat(None if session == "new" else session, message)
        return req.res.json({"session_id": answer.session_id})


async def test_summaries_after_transactional_requests(make_app, client_for, tmp_path):
    Chat.service_provider = SummarizingProvider()
    app = make_app(
        controllers=[TransactionalChat],
        extensions=[SumDatabases],
        SUM_DB=SqlDatabaseConfig(
            DATABASE_URI=f"sqlite+aiosqlite:///{tmp_path / 's.db'}"
        ),
        CHAT=CONFIG.model_copy(update={"HISTORY_LIMIT": 2, "HISTORY_SUMMARY": SUMMARY}),
    )
    db = app.get_extension(SumDatabases).get_database("summaries")
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(SumBase.metadata.create_all, tables=[SumRow.__table__])
    async with client_for(app) as client:
        sid = (await client.post("/chat/new/one")).json()["session_id"]
        await client.post(f"/chat/{sid}/two")
        # The update runs after the request, in its own context and session.
        await wait_for_background_tasks(None)
        service = app.get_extension(Chat)
        assert await service.history_provider.load_summary(sid) == HistorySummary(
            "S1[one]", 1
        )


def _pair(number: int) -> list[ChatMessage]:
    return [
        ChatMessage(role="user", content=f"q{number}"),
        ChatMessage(role="assistant", content=f"a{number}"),
    ]


async def test_concurrent_writes_to_one_session_get_distinct_positions(chat):
    history_provider = chat.history_provider
    await asyncio.gather(*(history_provider.append("s", _pair(n)) for n in range(6)))
    stored = await history_provider.load_since("s", None, None)
    assert [item.position for item in stored] == list(range(12))
    # Each question is directly followed by its own answer.
    for question, answer in zip(stored[::2], stored[1::2]):
        assert question.message.content[1:] == answer.message.content[1:]


async def test_only_one_first_summary_is_saved(chat):
    history_provider = chat.history_provider
    results = await asyncio.gather(
        *(
            history_provider.save_summary("s", HistorySummary(f"S{n}", 1), None)
            for n in range(4)
        )
    )
    assert results.count(True) == 1
    rows = [r for r in await _rows(chat) if r[1] == "summary"]
    assert len(rows) == 1


async def test_two_application_engines_do_not_collide(chat, make_app):
    """
    Two applications with engines of their own stand in for two worker
    processes. Only the database lock keeps their writes apart.
    """
    db = chat.app.get_extension(SumDatabases).get_database("summaries")
    other_app = make_app(
        extensions=[SumDatabases],
        SUM_DB=SqlDatabaseConfig(DATABASE_URI=db.db_uri),
        CHAT=chat.configs,
    )
    other = Chat(other_app)
    other_db = other_app.get_extension(SumDatabases).get_database("summaries")
    await other_db.connect()
    try:
        await asyncio.gather(
            *(
                (chat if n % 2 else other).history_provider.append("s", _pair(n))
                for n in range(8)
            )
        )
        firsts = await asyncio.gather(
            chat.history_provider.save_summary("s", HistorySummary("A", 1), None),
            other.history_provider.save_summary("s", HistorySummary("B", 1), None),
        )
    finally:
        await other_db.disconnect()
    stored = await chat.history_provider.load_since("s", None, None)
    assert [item.position for item in stored] == list(range(16))
    assert sorted(firsts) == [False, True]


def _history_worker(uri, root, barrier, number):
    """Spawn target: each worker owns its application, loop, and DB engine."""
    from pathlib import Path
    from tests.helpers import AppFactory

    async def run():
        factory = AppFactory(Path(root))
        app = factory(
            extensions=[SumDatabases],
            SUM_DB=SqlDatabaseConfig(DATABASE_URI=uri),
            CHAT=CONFIG,
        )
        service = Chat(app)
        database = app.get_extension(SumDatabases).get_database("summaries")
        await database.connect()
        try:
            await asyncio.to_thread(barrier.wait, 20)
            for index in range(4):
                await service.history_provider.append(
                    "processes", _pair(number * 4 + index)
                )
            await service.history_provider.save_summary(
                "processes", HistorySummary(f"worker {number}", 1), None
            )
        finally:
            await database.disconnect()
            factory.cleanup()

    asyncio.run(run())


async def test_spawned_processes_do_not_collide(chat, tmp_path):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    database = chat.app.get_extension(SumDatabases).get_database("summaries")
    workers = []
    try:
        for number in range(2):
            root = tmp_path / f"worker-{number}"
            root.mkdir()
            worker = context.Process(
                target=_history_worker,
                args=(database.db_uri, str(root), barrier, number),
            )
            worker.start()
            workers.append(worker)
        for worker in workers:
            await asyncio.to_thread(worker.join, 40)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                await asyncio.to_thread(worker.join, 5)
            worker.close()
    rows = await chat.history_provider.load_since("processes", None, None)
    assert [row.position for row in rows] == list(range(16))
    assert {row.message.content for row in rows} == {
        f"{role}{number}" for role in ("q", "a") for number in range(8)
    }
    for question, answer in zip(rows[::2], rows[1::2]):
        assert question.message.content[1:] == answer.message.content[1:]
    assert await chat.history_provider.load_summary("processes") is not None


async def _transactional_request(app, work) -> None:
    """Runs ``work`` the way a @transactional request does: commit at the end."""
    from patera.ctx import request_context
    from patera.database.sql.request_keys import TRANSACTION_OPEN

    manager = app.get_extension(SumDatabases)
    with request_context(app=app) as ctx:
        ctx.extras[TRANSACTION_OPEN] = True
        try:
            await work()
            ctx.extras.pop(TRANSACTION_OPEN)
            await manager.commit_all_sessions(ctx.sessions)
        finally:
            await manager.close_all_sessions(ctx)


async def test_overlapping_transactional_requests_on_one_chat(chat):
    """
    The first request writes, works on, writes again and only then commits.
    The second writes in between: it must wait for that commit instead of
    reusing order numbers it cannot see yet, and must not block the first
    request's second write while it waits.
    """
    history_provider = chat.history_provider
    first_wrote = asyncio.Event()

    async def first() -> None:
        await history_provider.append("s", _pair(1))
        first_wrote.set()
        await asyncio.sleep(0.3)
        await history_provider.append("s", _pair(2))

    async def second() -> None:
        await first_wrote.wait()
        await history_provider.append("s", _pair(3))

    await asyncio.wait_for(
        asyncio.gather(
            _transactional_request(chat.app, first),
            _transactional_request(chat.app, second),
        ),
        timeout=10,
    )
    stored = await history_provider.load_since("s", None, None)
    assert [item.position for item in stored] == list(range(6))
    assert [item.message.content for item in stored] == [
        "q1",
        "a1",
        "q2",
        "a2",
        "q3",
        "a3",
    ]


async def test_databases_without_a_lock_take_turns_in_process(chat, monkeypatch):
    """MySQL and others: the in-process lock is held until each write commits."""
    from patera.aiinterface.history_provider import base_history_provider

    monkeypatch.setattr(base_history_provider, "_LOCKING_DIALECTS", frozenset())
    history_provider = chat.history_provider
    await asyncio.gather(*(history_provider.append("s", _pair(n)) for n in range(6)))
    stored = await history_provider.load_since("s", None, None)
    assert [item.position for item in stored] == list(range(12))
