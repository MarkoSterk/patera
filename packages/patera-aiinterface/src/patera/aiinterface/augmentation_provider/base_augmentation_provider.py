"""
Retrieval augmentation (RAG) provider.

Needs the optional embedding libraries, installed with
``pip install "patera-aiinterface[augmentation]"``. The AI service checks for
them when it starts; the model is loaded the first time a text is embedded,
so CLI commands and tests that never search do not load it.

The documents live in a table with a text column and a vector column
(``VectorColumn``, pgvector's type)::

    class Document(Base):
        __tablename__ = "documents"
        id: Mapped[int] = mapped_column(primary_key=True)
        text: Mapped[str] = mapped_column(Text)
        vector = mapped_column(VectorColumn(384))   # the model's dimension

    class Documents(BaseAugmentationProvider[Document]):
        model = Document

Add documents with ``add_documents()``, which embeds them with the same model
that later embeds the questions. On PostgreSQL the search is one pgvector
query; on other databases the candidates are compared in Python.
"""

from __future__ import annotations

import asyncio
import importlib.util
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Optional, Sequence, Type, TypeVar, cast

from sqlalchemy import Select, select
from sqlalchemy.engine import make_url

from patera import Request
from patera.database.sql import DeclarativeBaseModel, SqlDatabase

from .config import AugmentationConfig

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

    from ..ai_service import AiService


ModelT = TypeVar("ModelT", bound=DeclarativeBaseModel)

MISSING_EXTRA = (
    "Retrieval augmentation needs the optional embedding libraries: "
    'pip install "patera-aiinterface[augmentation]"'
)


def _import_sentence_transformer() -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError(MISSING_EXTRA) from exc
    return SentenceTransformer


class BaseAugmentationProvider(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(
        self,
        *,
        vector_column: str = "vector",
        text_column: str = "text",
    ) -> None:
        self._embedding_model: Optional[SentenceTransformer] = None
        self._model_lock = threading.Lock()
        self._configs: AugmentationConfig = AugmentationConfig.model_validate({})
        self._vector_column = vector_column
        self._text_column = text_column
        self._ext: Optional["AiService[Any, Any]"] = None

    # ---- setup ----------------------------------------------------------------

    def bind(self, configs: AugmentationConfig, ext: "AiService[Any, Any]") -> None:
        """
        Called once by the AI service. Fails early when the default embedding
        model is used without the "augmentation" extra; the model itself is
        loaded on first use (see embedding_model).
        """
        uses_default_model = (
            type(self).load_embedding_model
            is BaseAugmentationProvider.load_embedding_model
        )
        if (
            uses_default_model
            and importlib.util.find_spec("sentence_transformers") is None
        ):
            raise ImportError(MISSING_EXTRA)
        self._configs = configs
        self._ext = ext
        self._embedding_model = None

    def load_embedding_model(self) -> Any:
        """
        Loads the embedding model (a sentence-transformers model by default,
        cached in CACHE_FOLDER relative to BASE_PATH). Override it to use
        another model with ``encode(text | list[str])``.
        """
        if self._ext is None:
            raise RuntimeError(
                f"{type(self).__name__} is not attached to an AI service."
            )
        sentence_transformer = _import_sentence_transformer()
        configs = self._configs
        base = Path(self._ext.app.configs.BASE_PATH)
        cache_folder = Path(configs.CACHE_FOLDER).expanduser()
        cache = (
            cache_folder if cache_folder.is_absolute() else base / cache_folder
        ).resolve()
        return sentence_transformer(
            model_name_or_path=configs.MODEL_NAME_OR_PATH,
            device=configs.DEVICE,
            backend=configs.BACKEND,
            cache_folder=str(cache),
        )

    @property
    def embedding_model(self) -> Any:
        """The embedding model, loaded the first time it is needed."""
        if self._embedding_model is None:
            with self._model_lock:
                if self._embedding_model is None:
                    self._embedding_model = self.load_embedding_model()
        return self._embedding_model

    def _database(self) -> SqlDatabase:
        if self._ext is None:
            raise RuntimeError(
                f"{type(self).__name__} is not attached to an AI service."
            )
        database = self._ext.app.extensions.get(self.model.db_name())
        if database is None:
            raise RuntimeError(
                f"No database {self.model.db_name()!r} found for {self.model.__name__}."
            )
        return cast(SqlDatabase, database)

    # ---- embeddings and documents ----------------------------------------------

    def embed(self, text: str) -> list[float]:
        """The embedding of a text, as stored in the vector column."""
        return [float(x) for x in self.embedding_model.encode(text)]

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            [float(x) for x in vector]
            for vector in self.embedding_model.encode(list(texts))
        ]

    async def add_documents(self, texts: Sequence[str], **columns: Any) -> list[ModelT]:
        """
        Embeds and stores documents. ``columns`` are set on every new row
        (for example ``owner_id=7``). Returns the new rows.
        """
        rows: list[ModelT] = []
        vectors = await asyncio.to_thread(self.embed_many, list(texts))
        for text, vector in zip(texts, vectors):
            row = self.model()
            setattr(row, self._text_column, text)
            setattr(row, self._vector_column, vector)
            for name, value in columns.items():
                setattr(row, name, value)
            rows.append(row)
        async with self._database().work_session() as session:
            session.add_all(rows)
            await session.flush()
            # Detach the new rows with their values loaded, so they stay readable.
            for row in rows:
                session.expunge(row)
        return rows

    async def add_document(self, text: str, **columns: Any) -> ModelT:
        return (await self.add_documents([text], **columns))[0]

    # ---- retrieval --------------------------------------------------------------

    def base_query(self, req: Optional[Request]) -> Select[Any]:
        """
        The candidate documents. Override it to filter, for example by user:
        ``return select(self.model).where(self.model.owner_id == req.user.id)``
        (``req`` is None outside a request).
        """
        return select(self.model)

    def uses_database_search(self) -> bool:
        """
        True when the search runs as a pgvector query in the database. With
        RETRIEVAL "auto", decided from the database URI, so it works before
        the database has connected (in a CLI command, for example).
        """
        mode = self._configs.RETRIEVAL
        if mode != "auto":
            return mode == "database"
        return make_url(self._database().db_uri).get_backend_name() == "postgresql"

    async def search(self, query: str, req: Optional[Request] = None) -> list[ModelT]:
        """
        The MATCH_LIMIT documents most similar to the query, most similar
        first, leaving out those below MINIMAL_SIMILARITY.
        """
        # In a thread: loading the model and encoding are CPU work.
        embedding = await asyncio.to_thread(self.embed, query)
        if self.uses_database_search():
            return await self._search_in_database(embedding, req)
        return await self._search_in_python(embedding, req)

    async def relevant_texts(
        self, query: str, req: Optional[Request] = None
    ) -> list[str]:
        """Texts of the documents found by search()."""
        return [
            getattr(document, self._text_column)
            for document in await self.search(query, req)
        ]

    async def _search_in_database(
        self, embedding: list[float], req: Optional[Request]
    ) -> list[ModelT]:
        column = getattr(self.model, self._vector_column)
        if not hasattr(column, "cosine_distance"):
            raise TypeError(
                f"{self.model.__name__}.{self._vector_column} must be a VectorColumn "
                "(pgvector) for database search; set RETRIEVAL='python' otherwise."
            )
        distance = column.cosine_distance(embedding)
        statement = (
            self.base_query(req)
            .where(distance <= 1 - self._configs.MINIMAL_SIMILARITY)
            .order_by(distance)
            .limit(self._configs.MATCH_LIMIT)
        )
        async with self._database().work_session() as session:
            documents = list((await session.execute(statement)).scalars().all())
            for document in documents:
                session.expunge(document)
        return documents

    async def _search_in_python(
        self, embedding: list[float], req: Optional[Request]
    ) -> list[ModelT]:
        async with self._database().work_session() as session:
            documents = list(
                (await session.execute(self.base_query(req))).scalars().all()
            )
            for document in documents:
                session.expunge(document)
        return self.rank(embedding, documents)

    def rank(
        self, embedding: Sequence[float], documents: Sequence[ModelT]
    ) -> list[ModelT]:
        """Orders documents by cosine similarity to the embedding (in Python)."""
        import numpy as np

        if not documents:
            return []
        query = np.asarray(embedding, dtype=np.float32)
        vectors = np.asarray(
            [getattr(document, self._vector_column) for document in documents],
            dtype=np.float32,
        )
        norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
        norms[norms == 0] = 1.0  # a zero vector scores 0 instead of NaN
        scores = (vectors @ query) / norms
        ranked = sorted(
            zip(documents, scores.tolist()), key=lambda pair: pair[1], reverse=True
        )
        return [
            document
            for document, score in ranked[: self._configs.MATCH_LIMIT]
            if score >= self._configs.MINIMAL_SIMILARITY
        ]
