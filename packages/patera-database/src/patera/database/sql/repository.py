"""
Repository base for the repository pattern
"""

from __future__ import annotations

from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


T = TypeVar("T", bound=Base)


class Repository(Generic[T]):
    model: Type[T]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls is not Repository and "model" not in cls.__dict__:
            raise TypeError(f"{cls.__name__} must define a 'model' class attribute")

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: int) -> T | None:
        return self.session.get(self.model, entity_id)

    def list_all(self) -> list[T]:
        return list(self.session.scalars(select(self.model)).all())

    def create(self, **kwargs) -> T:
        entity = self.model(**kwargs)
        self.session.add(entity)
        return entity

    def add(self, entity: T) -> T:
        self.session.add(entity)
        return entity

    def delete(self, entity: T) -> None:
        self.session.delete(entity)
