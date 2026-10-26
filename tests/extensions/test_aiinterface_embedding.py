"""Opt-in real model test: PATERA_TEST_EMBEDDING_MODEL is a cached model path."""

import os

import pytest
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

pytest.importorskip("patera.aiinterface")

from patera.aiinterface import AugmentationConfig  # noqa: E402
from patera.aiinterface.augmentation_provider import BaseAugmentationProvider  # noqa: E402
from patera.database.sql import SqlDatabaseConfig  # noqa: E402
from tests.extensions.test_aiinterface import CONFIG  # noqa: E402
from tests.extensions.test_aiinterface_documents import (  # noqa: E402
    BACKENDS,
    DocBase,
    DocsDatabases,
    Librarian,
    VectorColumn,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("PATERA_TEST_EMBEDDING_MODEL"), reason="real model is opt-in"
    ),
]


class RealDocument(DocBase):
    __tablename__ = "ai_real_embedding_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    vector = mapped_column(VectorColumn(384))


class RealDocuments(BaseAugmentationProvider[RealDocument]):
    model = RealDocument


@pytest.mark.parametrize("backend", BACKENDS)
async def test_real_model_ingestion_and_retrieval(
    make_app, tmp_path, monkeypatch, backend
):
    monkeypatch.setattr(Librarian, "augmentation_provider", RealDocuments())
    config = AugmentationConfig(
        MODEL_NAME_OR_PATH=os.environ["PATERA_TEST_EMBEDDING_MODEL"],
        DEVICE="cpu",
        CACHE_FOLDER=str(tmp_path / "cache"),
        MINIMAL_SIMILARITY=0.25,
        MATCH_LIMIT=1,
    )
    app = make_app(
        extensions=[DocsDatabases],
        DOCS_DB=SqlDatabaseConfig(
            DATABASE_URI=(
                os.environ["PATERA_TEST_PG_URI"]
                if backend == "postgresql"
                else f"sqlite+aiosqlite:///{tmp_path / 'real.db'}"
            )
        ),
        LIBRARIAN=CONFIG.model_copy(update={"AUGMENTATION": config}),
    )
    database = app.get_extension(DocsDatabases).get_database("docs")
    await database.connect()
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(
                DocBase.metadata.drop_all, tables=[RealDocument.__table__]
            )
            await connection.run_sync(
                DocBase.metadata.create_all, tables=[RealDocument.__table__]
            )
        service = Librarian(app)
        provider = service.augmentation_provider
        assert provider._embedding_model is None
        await provider.add_documents(
            [
                "The cat sleeps on a sofa.",
                "Database transactions use locks.",
            ]
        )
        model = provider.embedding_model
        found = await provider.relevant_texts("A kitten rests on the couch.")
        assert found == ["The cat sleeps on a sofa."]
        assert provider.embedding_model is model
        # A new provider loads the downloaded model again without network access.
        second = Librarian(app).augmentation_provider
        assert await second.relevant_texts("A kitten rests on the couch.") == found
    finally:
        async with database.engine.begin() as connection:
            await connection.run_sync(
                DocBase.metadata.drop_all, tables=[RealDocument.__table__]
            )
        await database.disconnect()
