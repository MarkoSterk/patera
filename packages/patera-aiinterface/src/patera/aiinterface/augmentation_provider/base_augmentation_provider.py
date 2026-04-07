"""
RAG interface
"""

from typing import (
    Any,
    Generic,
    Type,
    TypeVar,
    Optional,
    TypedDict,
    NotRequired,
    cast,
    TYPE_CHECKING,
)
from sentence_transformers import SentenceTransformer
from torch import Tensor
from patera import Request
from patera.database.sql import DeclarativeBaseModel

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


ModelT = TypeVar("ModelT", bound=DeclarativeBaseModel)


class _AugmentationConfig(BaseModel):
    """
    Configuration for augmentation provider
    Check sentence_transformers.SentenceTransformer for more details on the parameters
    """

    MODEL_NAME_OR_PATH: Optional[str] = Field(
        "all-MiniLM-L6-v2", description="Model name or path for the embedding model"
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
    MINIMAL_SIMILARITY: Optional[float] = Field(
        0.9, description="Minimal similarity for documents to be used for augmentation"
    )


class AugmentationConfig(TypedDict):
    MODEL_NAME_OR_PATH: NotRequired[str]
    MODULES: NotRequired[list[str]]
    DEVICE: NotRequired[str]
    CACHE_FOLDER: NotRequired[str]
    BACKEND: NotRequired[str]
    MINIMAL_SIMILARITY: NotRequired[float]


class BaseAugmentationProvider(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(
        self,
        *,
        vector_column: str = "vector",
        text_column: str = "text",
        retriever_limit: int = 5,
    ) -> None:
        self._embedding_model: SentenceTransformer = cast(SentenceTransformer, None)
        self._configs: dict = cast(dict, None)
        self._vector_column = vector_column
        self._text_column = text_column
        self._retriever_limit = retriever_limit
        self._initilized: bool = False

    def _init_embedding_model(self, configs: dict[Any, Any]) -> None:
        """
        Initialize embedding model
        """
        self._configs = configs
        self._embedding_model = SentenceTransformer(
            model_name_or_path=self._configs["MODEL_NAME_OR_PATH"],
            modules=self._configs["MODULES"],
            device=self._configs["DEVICE"],
            backend=self._configs["BACKEND"],
            cache_folder=self._configs["CACHE_FOLDER"],
        )
        self._initilized = True

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
        embeddings = [
            Tensor(getattr(document, self._vector_column)) for document in documents
        ]
        similarities = [
            self._embedding_model.similarity(query_embedding, embedding)
            for embedding in embeddings
        ]
        sorted_documents = sorted(
            zip(documents, similarities), key=lambda x: x[1], reverse=True
        )
        documents = [
            document
            for document, sim in sorted_documents[: self._retriever_limit]
            if sim >= self._configs.get("MINIMAL_SIMILARITY", 0.9)
        ]
        return documents
