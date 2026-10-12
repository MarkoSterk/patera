"""
Configuration of the augmentation provider. Kept apart from the provider so
that the AI service can import it without the optional embedding libraries.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_CONTEXT_TEMPLATE = (
    "Documents that may help with the next message. Use them when they are "
    "relevant and ignore them otherwise.\n\n<:documents>"
)

DEFAULT_REWRITE_PROMPT = (
    "Rewrite the user's follow-up question as a standalone question that can be "
    "understood without the conversation; it is used to search documents. Keep "
    "the language of the question. Reply with the question only."
)


class AugmentationConfig(BaseModel):
    """
    Settings for retrieval augmentation (AiServiceConfig.AUGMENTATION).
    See sentence_transformers.SentenceTransformer for the model options.
    """

    MODEL_NAME_OR_PATH: str = Field(
        "all-MiniLM-L6-v2", description="Model name or path for the embedding model"
    )
    DEVICE: Optional[str] = Field(
        None, description="Device to use for embedding model (e.g., 'cpu', 'cuda')"
    )
    CACHE_FOLDER: str = Field(
        ".ai_cache",
        description="Download cache of the embedding model, relative to BASE_PATH",
    )
    BACKEND: Literal["torch", "onnx", "openvino"] = Field(
        "torch",
        description="Backend to use for the embedding model ('torch', 'onnx', 'openvino')",
    )
    MINIMAL_SIMILARITY: float = Field(
        0.9,
        description="Minimal cosine similarity for a document to be used (-1 to 1)",
    )
    MATCH_LIMIT: int = Field(
        5, ge=1, description="Maximum number of documents added to a call"
    )
    RETRIEVAL: Literal["auto", "database", "python"] = Field(
        "auto",
        description=(
            "Where documents are compared with the question: 'database' runs a "
            "pgvector query (PostgreSQL), 'python' loads the candidates and "
            "compares them in Python (any database), 'auto' uses the database "
            "on PostgreSQL and Python elsewhere."
        ),
    )
    CONTEXT_TEMPLATE: str = Field(
        DEFAULT_CONTEXT_TEMPLATE,
        description=(
            "Text of the context message sent before the user message; "
            "<:documents> is replaced by the numbered documents."
        ),
    )
    REWRITE_QUERY: bool = Field(
        False,
        description=(
            "With @history, ask the model to turn a follow-up question into a "
            "standalone one before searching (one extra model call per message)."
        ),
    )
    REWRITE_PROMPT: str = Field(
        DEFAULT_REWRITE_PROMPT,
        description="System prompt of the question-rewriting call",
    )
