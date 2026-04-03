"""
RAG interface
"""

from typing import Generic, Type, TypeVar, Optional, TypedDict, NotRequired, cast
from sentence_transformers import SentenceTransformer
from patera import Request
from patera.database.sql import DeclarativeBaseModel

from pydantic import BaseModel, Field


ModelT = TypeVar("ModelT", bound=DeclarativeBaseModel)


class _AugmentationConfig(BaseModel):
    """
    Configuration for augmentation provider
    Check sentence_transformers.SentenceTransformer for more details on the parameters
    """

    MODEL_NAME_OR_PATH: str = Field(
        ..., description="Model name or path for the embedding model"
    )
    MODULES: Optional[list[str]] = Field(
        None, description="List of modules to use for augmentation"
    )
    DEVICE: Optional[str] = Field(
        None, description="Device to use for embedding model (e.g., 'cpu', 'cuda')"
    )
    CACHE_FOLDER: Optional[str] = Field(
        None, description="Cache folder for the embedding model"
    )
    BACKEND: Optional[str] = Field(
        "torch",
        description="Backend to use for the embedding model ('torch', 'onnx', 'openvino')",
    )


class AugmentationConfig(TypedDict):
    MODEL_NAME_OR_PATH: str
    MODULES: NotRequired[list[str]]
    DEVICE: NotRequired[str]
    CACHE_FOLDER: NotRequired[str]
    BACKEND: NotRequired[str]


class BaseAugmentationProvider(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(
        self,
        vector_column: str = "vector",
        text_column: str = "text",
        retriever_limit: int = 5,
    ) -> None:
        self._embedding_model: SentenceTransformer = cast(SentenceTransformer, None)
        self._configs: Optional[dict] = None
        self._vector_column = vector_column
        self._text_column = text_column
        self._retriever_limit = retriever_limit

    def _init_embedding_model(self, configs: Optional[dict] = None) -> None:
        """
        Initialize embedding model
        """
        if configs is None:
            configs = {}
        self._configs = {
            key.lower(): value
            for key, value in _AugmentationConfig.model_validate(configs)
            .model_dump()
            .items()
        }
        self._embedding_model = SentenceTransformer(**self._configs)

    async def _augment_prompt(self, req: Request, prompt: str) -> list[str]:
        """
        Augment prompt with relevant information
        """
        documents = await self.retriever(req, prompt)
        prompt_augmentation = [
            getattr(document, self._text_column) for document in documents
        ]
        return prompt_augmentation

    async def loader(self, req: Request) -> list[ModelT]:
        """
        Loads documents for augmentation. By default, it loads all documents from the database.
        You can override this method to implement custom loading logic (e.g., filtering for users, chat sessions etc.)
        """
        return await self.model.query().all()

    async def retriever(self, req: Request, query: str) -> list[ModelT]:
        """
        Retrieve and select relevant information based on query
        """
        query_embedding = self._embedding_model.encode(query)
        documents = await self.loader(req)
        embeddings = [getattr(document, self._vector_column) for document in documents]
        similarities = [
            self._embedding_model.similarity(query_embedding, embedding)
            for embedding in embeddings
        ]
        sorted_documents = sorted(
            zip(documents, similarities), key=lambda x: x[1], reverse=True
        )
        documents = [
            document for document, _ in sorted_documents[: self._retriever_limit]
        ]
        return documents
