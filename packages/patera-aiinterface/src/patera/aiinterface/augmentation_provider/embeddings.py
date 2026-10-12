"""
Vector column type for augmentation documents.

``VectorColumn`` is pgvector's SQLAlchemy type. On PostgreSQL (with the
pgvector extension) it enables the database search; on other databases the
vectors are stored as text and compared in Python. Needs
``pip install "patera-aiinterface[augmentation]"``.
"""

try:
    from pgvector.sqlalchemy import Vector as VectorColumn
except ImportError as exc:  # pragma: no cover - depends on the installed extra
    from .base_augmentation_provider import MISSING_EXTRA

    raise ImportError(MISSING_EXTRA) from exc

__all__ = ["VectorColumn"]
