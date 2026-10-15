"""
Augmentation documents in a real database: SQLite (vectors compared in Python)
and, when PATERA_TEST_PG_URI points at a PostgreSQL server with the pgvector
extension, PostgreSQL (one pgvector query).
"""

from __future__ import annotations

import os
from typing import Optional

import pytest
from sqlalchemy import Integer, Text, select
from sqlalchemy.orm import Mapped, mapped_column

pytest.importorskip("patera.aiinterface")
pytest.importorskip("numpy")
pgvector_sqlalchemy = pytest.importorskip("pgvector.sqlalchemy")
VectorColumn = pgvector_sqlalchemy.Vector

from patera.aiinterface import (  # noqa: E402
    AiService,
    AugmentationConfig,
    ChatResponse,
    augmentation,
    system_prompt,
    user_prompt,
)
from patera.aiinterface.augmentation_provider import BaseAugmentationProvider  # noqa: E402
from patera.database.sql import (  # noqa: E402
    DeclarativeBaseModel,
    SqlDatabase,
    SqlDatabaseConfig,
    SqlDatabaseManager,
)

from tests.extensions.test_aiinterface import CONFIG, FakeProvider  # noqa: E402

pytestmark = pytest.mark.integration


class KeywordModel:
    """A tiny embedding model: counts of cat, dog and car (plus a small floor)."""

    words = ("cat", "dog", "car")

    def _one(self, text: str) -> list[float]:
        lowered = text.lower()
        return [lowered.count(word) + 0.01 for word in self.words]

    def encode(self, texts):
        import numpy as np

        if isinstance(texts, str):
            return np.asarray(self._one(texts))
        return np.asarray([self._one(t) for t in texts])


class DocBase(DeclarativeBaseModel):
    __abstract__ = True
    __db_name__ = "docs"


class Doc(DocBase):
    __tablename__ = "ai_test_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    owner: Mapped[int] = mapped_column(Integer, default=0)
    vector = mapped_column(VectorColumn(3))


class DocsDb(SqlDatabase):
    __db_name__ = "docs"


class DocsDatabases(SqlDatabaseManager):
    databases = [DocsDb]


class Documents(BaseAugmentationProvider[Doc]):
    model = Doc
    only_owner: Optional[int] = None

    loads = 0

    def load_embedding_model(self):
        # A small model instead of sentence-transformers.
        type(self).loads += 1
        return KeywordModel()

    def base_query(self, req):
        query = super().base_query(req)
        if self.only_owner is not None:
            query = query.where(Doc.owner == self.only_owner)
        return query


class Librarian(AiService):
    service_provider = FakeProvider()
    augmentation_provider = Documents()

    @augmentation
    @system_prompt("Answer from the documents.")
    @user_prompt("<:question>")
    async def ask(self, question: str) -> ChatResponse: ...


BACKENDS = ["sqlite"] + (["postgresql"] if os.environ.get("PATERA_TEST_PG_URI") else [])


@pytest.fixture(params=BACKENDS)
async def librarian(request, make_app, tmp_path):
    if request.param == "sqlite":
        uri = f"sqlite+aiosqlite:///{tmp_path / 'docs.db'}"
    else:
        uri = os.environ["PATERA_TEST_PG_URI"]
    Librarian.service_provider = FakeProvider()
    Librarian.augmentation_provider = Documents()
    app = make_app(
        extensions=[DocsDatabases],
        DOCS_DB=SqlDatabaseConfig(DATABASE_URI=uri),
        LIBRARIAN=CONFIG.model_copy(
            update={
                "AUGMENTATION": AugmentationConfig(
                    MINIMAL_SIMILARITY=0.8, MATCH_LIMIT=2
                )
            }
        ),
    )
    db = app.get_extension(DocsDatabases).get_database("docs")
    await db.connect()
    async with db.engine.begin() as conn:
        await conn.run_sync(DocBase.metadata.drop_all, tables=[Doc.__table__])
        await conn.run_sync(DocBase.metadata.create_all, tables=[Doc.__table__])
    service = Librarian(app)
    await service.augmentation_provider.add_documents(
        [
            "Our cat sleeps all day. The cat likes boxes.",
            "A cat and a dog share the garden.",
            "The dog barks at the car.",
            "Car maintenance: change the oil of the car every year.",
        ]
    )
    await service.augmentation_provider.add_document("Another cat story.", owner=7)
    yield request.param, service
    async with db.engine.begin() as conn:
        await conn.run_sync(DocBase.metadata.drop_all, tables=[Doc.__table__])
    await db.disconnect()


async def test_documents_are_stored_with_their_embeddings(librarian):
    backend, service = librarian
    provider = service.augmentation_provider
    row = await provider.add_document("A cat.", owner=3)
    assert row.id is not None and row.owner == 3 and row.text == "A cat."
    db = service.app.get_extension(DocsDatabases).get_database("docs")
    async with db.session_scope() as session:
        stored = (
            await session.execute(select(Doc).where(Doc.id == row.id))
        ).scalar_one()
        assert [round(float(x), 2) for x in stored.vector] == [1.01, 0.01, 0.01]


async def test_search_finds_the_most_similar_documents(librarian):
    backend, service = librarian
    provider = service.augmentation_provider
    assert provider.uses_database_search() is (backend == "postgresql")

    texts = await provider.relevant_texts("Tell me about the cat")
    # Ranked by similarity, at most MATCH_LIMIT=2, the dog/car texts are below 0.8.
    assert texts == [
        "Another cat story.",
        "Our cat sleeps all day. The cat likes boxes.",
    ]
    assert await provider.relevant_texts("cars and oil") == [
        "Car maintenance: change the oil of the car every year."
    ]
    # Every dog text also mentions a cat or a car: none reaches 0.8 for "dog".
    assert await provider.relevant_texts("a dog") == []


async def test_base_query_filters_the_candidates(librarian):
    backend, service = librarian
    provider = service.augmentation_provider
    provider.only_owner = 7
    assert await provider.relevant_texts("cat") == ["Another cat story."]
    provider.only_owner = 0
    assert "Another cat story." not in await provider.relevant_texts("cat")


async def test_python_search_can_be_forced(librarian):
    backend, service = librarian
    provider = service.augmentation_provider
    provider._configs = provider._configs.model_copy(update={"RETRIEVAL": "python"})
    assert provider.uses_database_search() is False
    texts = await provider.relevant_texts("Tell me about the cat")
    assert texts == [
        "Another cat story.",
        "Our cat sleeps all day. The cat likes boxes.",
    ]


async def test_retrieved_documents_reach_the_model(librarian):
    backend, service = librarian
    await service.ask("Is there a dog and a cat?")
    context = service.service_provider.sent[0][1]
    assert context[0] == "system"
    assert "[1] A cat and a dog share the garden." in context[1]


async def test_the_embedding_model_is_loaded_on_first_use_only(librarian):
    import asyncio

    backend, service = librarian
    fresh = Librarian(service.app)  # e.g. what a CLI command creates
    loads = Documents.loads
    assert fresh.augmentation_provider._embedding_model is None
    assert Documents.loads == loads  # starting the service loaded nothing

    await asyncio.gather(
        fresh.augmentation_provider.relevant_texts("cat"),
        fresh.augmentation_provider.relevant_texts("dog"),
    )
    assert Documents.loads == loads + 1  # once, even for concurrent first uses
    await fresh.augmentation_provider.relevant_texts("car")
    assert Documents.loads == loads + 1


async def test_search_works_before_the_database_connects(librarian):
    """A CLI command, for example, searches before anything connected."""
    backend, service = librarian
    db = service.app.get_extension(DocsDatabases).get_database("docs")
    await db.disconnect()
    provider = service.augmentation_provider
    assert provider.uses_database_search() is (backend == "postgresql")
    texts = await provider.relevant_texts("cat")
    assert texts and all("cat" in text.lower() for text in texts)
