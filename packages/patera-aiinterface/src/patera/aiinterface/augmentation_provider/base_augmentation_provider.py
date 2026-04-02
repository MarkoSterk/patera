"""
RAG interface
"""

from typing import Generic, Type, TypeVar
from patera.database.sql import DeclarativeBaseModel

ModelT = TypeVar("ModelT", bound=DeclarativeBaseModel)


class BaseAugmentationProvider(Generic[ModelT]):
    model: Type[ModelT]
