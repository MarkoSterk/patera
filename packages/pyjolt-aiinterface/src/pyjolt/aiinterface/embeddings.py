"""
Helpers for creating embeddings
"""

import numpy as np
from torch import Tensor
from sentence_transformers import SentenceTransformer
from pgvector.sqlalchemy import Vector as VectorColumn

__all__ = [
    "l2_distance",
    "cosine_similarity",
    "cosine_distance",
    "create_embedding",
    "chunkify_text",
    "VectorColumn",
]


def l2_distance(
    vec1: list[float] | np.ndarray, vec2: list[float] | np.ndarray
) -> float:
    """
    Calculates l2 distance between two vectors

    :param vec1: first vector.
    :param vec2: second vector.
    """
    if isinstance(vec1, list):
        vec1 = np.array(vec1)
    if isinstance(vec2, list):
        vec2 = np.array(vec2)
    return np.sqrt(np.sum((np.array(vec1) - np.array(vec2)) ** 2))


def cosine_similarity(
    vec1: list[float] | np.ndarray, vec2: list[float] | np.ndarray
) -> float:
    """
    Calculates cosine similarity between two vectors

    :param vec1: first vector.
    :param vec2: second vector.
    """
    if isinstance(vec1, list):
        vec1 = np.array(vec1)
    if isinstance(vec2, list):
        vec2 = np.array(vec2)
    dot_product = np.dot(vec1, vec2)
    norm_vec1 = np.linalg.norm(vec1)
    norm_vec2 = np.linalg.norm(vec2)
    return dot_product / (norm_vec1 * norm_vec2)


def cosine_distance(
    vec1: list[float] | np.ndarray, vec2: list[float] | np.ndarray
) -> float:
    """
    Calculates cosine distance between two vectors

    :param vec1: first vector.
    :param vec2: second vector.
    :returns: cosine distance as 1 - cosimn_similarity(vec1, vec2)
    """
    similarity: float = cosine_similarity(vec1, vec2)
    return 1 - similarity  # Cosine distance is 1 - cosine similarity


def create_embedding(
    text: str,
    transformer: str = "infgrad/stella-base-en-v2",
    trust_remote_code: bool = True,
    **kwargs,
) -> Tensor:
    """
    Creates embedding for provided text with specified transformer

    :param text: text for which the embedding is created.
    :param transformer: sentence transfor that is used.
    :param trust_remote_code: if you allow code from the Hugging Face Hun repo to be executed locally
    :param kwargs: any keyword arguments that are accepted by the SentenceTransformer class
    """
    embedding_model = SentenceTransformer(
        transformer, trust_remote_code=trust_remote_code, **kwargs
    )
    return embedding_model.encode(text)


def chunkify_text(text: str, chunk_size: int) -> list[str]:
    """
    Takes a text and creates a list of chunks with words <= chunk_size

    :param text: the text to be chunkified.
    :param chunk_size: max number of words in chunk
    """
    words: list[str] = text.split()
    chunks: list[str] = []
    current_chunk: list[str] = []

    for word in words:
        current_chunk.append(word)
        if len(current_chunk) == chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
    if len(current_chunk) > 0:
        chunks.append(" ".join(current_chunk))
    return chunks
