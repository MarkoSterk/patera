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
    background_session,
    cli_session,
    in_transactional_request,
)
from .sqlalchemy_async_query import AsyncQuery
from .declarative_base import DeclarativeBaseModel
from .repository import Repository, query
from .sql_database_manager import SqlDatabaseManager, transactional

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
    "background_session",
    "in_transactional_request",
    "SqlDatabaseManager",
    "transactional",
]
