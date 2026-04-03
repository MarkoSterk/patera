"""
Helpers for creating embeddings
"""

import numpy as np
from pgvector.sqlalchemy import Vector as VectorColumn

__all__ = [
    "l2_distance",
    "cosine_similarity",
    "cosine_distance",
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
