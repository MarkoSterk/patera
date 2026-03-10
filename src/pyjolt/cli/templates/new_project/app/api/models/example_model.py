"""
Example data model
"""

from typing import Type
from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped

from pyjolt.database.sql import create_declarative_base, DeclarativeBaseModel

Base: Type[DeclarativeBaseModel] = create_declarative_base()


class Example(Base):  # type: ignore[valid-type,misc]
    """
    Example model
    """

    # table name in database; usually plural
    __tablename__: str = "examples"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
