"""
Helpers and constants for admin dashboard
"""

from typing import Optional, Type
from enum import StrEnum
from sqlalchemy.inspection import inspect
from ..database.sql.declarative_base import DeclarativeBaseModel


class FormType(StrEnum):
    CREATE = "create"
    UPDATE = "update"


class PermissionType(StrEnum):
    CAN_ENTER = "enter"
    CAN_VIEW = "view"
    CAN_CREATE = "create"
    CAN_UPDATE = "update"
    CAN_DELETE = "delete"


def extract_table_columns(
    Model: Type[DeclarativeBaseModel],
    exclude: Optional[list[str]] = None,
    limit: int = 8,
):
    """
    Extracts SQLAlchemy model columns suitable for displaying in a generic table.

    Rules:
      - Always include the primary key column(s) first.
      - Then include up to (limit - number_of_pk) additional columns
        sorted alphabetically by their attribute name.
      - Primary key(s) always appear first, even if alphabetically later.

    Args:
        Model: SQLAlchemy declarative model class.
        limit (int): Maximum number of columns to include (default = 8).

    Returns:
        list[Column]: Ordered list of SQLAlchemy Column objects.
    """
    if exclude is None:
        exclude = []
    mapper = inspect(Model)
    cols = list(mapper.columns)

    pk_keys = [c.key for c in cols if c.primary_key]
    non_pk_keys = sorted(
        [c.key for c in cols if not c.primary_key and c.key.lower() not in exclude],
        key=str.lower,
    )
    take = max(0, limit - len(pk_keys))
    return pk_keys + non_pk_keys[:take]


def register_model(model: Type):
    """
    Registers the model with the admin dashboard. Only
    registered models will appear in the dashboard.
    """
    setattr(model, "__use_in_dashboard__", True)
    return model
