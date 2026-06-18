"""
database module of patera
"""

# re-export of some commonly used sqlalchemy objects
# and methods for convenience.
from sqlalchemy import select, Select
from sqlalchemy.ext.asyncio import AsyncSession

from .sql_database import (
    SqlDatabase,
    SqlDatabaseConfig,
    cli_session,
)
from .sqlalchemy_async_query import AsyncQuery
from .declarative_base import DeclarativeBaseModel
from .repository import Repository, query
from .sql_database_manager import SqlDatabaseManager

__all__ = [
    "SqlDatabase",
    "select",
    "Select",
    "AsyncSession",
    "AsyncQuery",
    "DeclarativeBaseModel",
    "SqlDatabaseConfig",
    "Repository",
    "query",
    "cli_session",
    "SqlDatabaseManager",
]
