# base_protocol.py
# pylint: disable=W0613

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase

from patera import Patera
from patera.ctx import (
    current_request,
    get_request_context,
    ActiveSessions,
    has_request_context,
)

if TYPE_CHECKING:
    from .sqlalchemy_async_query import AsyncQuery
    from .sql_database import SqlDatabase


class MetaProtocol(Protocol):
    exclude_from_create_form: list[str]
    exclude_from_update_form: list[str]
    exclude_from_table: list[str]

    add_to_form: dict[str, type[Any]]

    custom_labels: dict[str, str]
    custom_form_fields: list[type[Any]]

    form_fields_order: list[str]
    order_table_by: list[str]

    create_validation_shema: type[BaseModel]
    update_validation_shema: type[BaseModel]


ModelT = TypeVar("ModelT", bound="DeclarativeBaseModel")


class DeclarativeBaseModel(DeclarativeBase):
    """
    Base class for framework ORM models.
    """

    __db_name__: str
    __db_configs_name__: str
    __abstract__ = True

    class Meta(MetaProtocol):
        exclude_from_create_form: list[str]
        exclude_from_update_form: list[str]
        exclude_from_table: list[str]

        add_to_form: dict[str, type[Any]]

        custom_labels: dict[str, str]
        custom_form_fields: list[type[Any]]

        form_fields_order: list[str]
        order_table_by: list[str]

        create_validation_shema: type[BaseModel]
        update_validation_shema: type[BaseModel]

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        if not cls.__abstract__ and "__db_name__" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define a class attribute '__db_name__'"
            )

    async def admin_create(
        self,
        new_data: dict[str, Any],
    ) -> None:
        for key, value in new_data.items():
            setattr(self, key, value)

    async def admin_delete(self) -> None:
        pass

    async def admin_update(
        self,
        new_data: dict[str, Any],
    ) -> None:
        for key, value in new_data.items():
            setattr(self, key, value)

    @classmethod
    def query(
        cls: type[ModelT],
        session: AsyncSession | None = None,
    ) -> AsyncQuery[ModelT]:
        """
        Creates an AsyncQuery object with provided session or
        with a created session. Requires an active request context.
        If a session already exists in the request context it is used to
        create the AsyncQuery object. If not, a new session is created, added
        to the request context and used in the AsyncQuery object.
        """
        from .sqlalchemy_async_query import AsyncQuery

        if session is not None:
            return AsyncQuery(
                session=session,
                model=cls,
            )

        if not has_request_context():
            raise RuntimeError(
                f"{cls.__name__}.query() requires an active request context "
                "when no explicit AsyncSession is provided."
            )

        database = cls.get_database()
        ctx = get_request_context()

        if ctx.sessions is None:
            ctx.sessions = ActiveSessions()

        session = ctx.sessions.get_session(database.session_name)

        if session is None:
            session = database.create_session()
            ctx.sessions.set_session(database.session_name, session)

        return AsyncQuery(
            session=session,
            model=cls,
        )

    @classmethod
    def get_database(cls) -> SqlDatabase:
        app: Patera = current_request.app
        database = app._extensions.get(cls.db_name(), None)
        if database is None:
            raise ValueError(f"Failed to find database {cls.db_name()}")
        return database  # type: ignore

    @classmethod
    def get_session(cls) -> AsyncSession:
        """
        Requires active request context
        Return active session from request context or creates a new one
        and stores it on the request context
        """
        if not has_request_context():
            raise RuntimeError(
                f"{cls.__name__}.get_session() requires an active request context "
                "when no explicit AsyncSession is provided."
            )
        database = cls.get_database()
        ctx = get_request_context()
        if ctx.sessions is None:
            ctx.sessions = ActiveSessions()
        session = ctx.sessions.get_session(database.session_name)
        if session is None:
            session = database.create_session()
            ctx.sessions.set_session(database.session_name, session)
        return session

    @classmethod
    def get_standalone_session(cls) -> AsyncSession:
        """
        Creates and returns an AsyncSession object.
        This is a standalone session object which is not taken from
        or stored to the request context
        """
        database = cls.get_database()
        return database.create_session()

    @classmethod
    def db_name(cls) -> str:
        return cls.__db_name__

    @classmethod
    def db_configs_name(cls) -> str:
        return cls.__db_configs_name__

    @classmethod
    def primary_key_names(cls) -> list[str | None] | None:
        mapper = inspect(cls)
        pks = mapper.primary_key

        if not pks:
            return None

        return [pk.key for pk in pks] if pks else None

    @classmethod
    def primary_keys(cls) -> tuple[Column[Any], ...] | None:
        mapper = inspect(cls)
        pks = mapper.primary_key

        if not pks:
            return None

        return cast(tuple[Column[Any], ...], tuple(pks))

    @classmethod
    def exclude_from_create_form(cls) -> list[str]:
        if not hasattr(cls.Meta, "exclude_from_create_form"):
            return []
        return cls.Meta.exclude_from_create_form

    @classmethod
    def exclude_from_update_form(cls) -> list[str]:
        if not hasattr(cls.Meta, "exclude_from_update_form"):
            return []
        return cls.Meta.exclude_from_update_form

    @classmethod
    def exclude_from_table(cls) -> list[str]:
        if not hasattr(cls.Meta, "exclude_from_table"):
            return []
        return cls.Meta.exclude_from_table

    @classmethod
    def form_labels_map(cls) -> dict[str, str]:
        if not hasattr(cls.Meta, "custom_labels"):
            return {}
        return cls.Meta.custom_labels

    @classmethod
    def custom_form_fields(cls) -> dict[str, type[Any]]:
        if not hasattr(cls.Meta, "custom_form_fields"):
            return {}
        return {field.id: field for field in cls.Meta.custom_form_fields}

    @classmethod
    def add_to_form(cls) -> dict[str, Any]:
        if not hasattr(cls.Meta, "add_to_form"):
            return {}
        return cls.Meta.add_to_form

    @classmethod
    def create_validation_schema(cls) -> type[BaseModel] | None:
        if not hasattr(cls.Meta, "create_validation_shema"):
            return None
        return cls.Meta.create_validation_shema

    @classmethod
    def update_validation_schema(cls) -> type[BaseModel] | None:
        if not hasattr(cls.Meta, "update_validation_shema"):
            return None
        return cls.Meta.update_validation_shema

    @classmethod
    def order_table_by(cls) -> list[str] | None:
        if not hasattr(cls.Meta, "order_table_by"):
            return None
        return cls.Meta.order_table_by

    @classmethod
    def form_fields_order(cls) -> list[str] | None:
        if not hasattr(cls.Meta, "form_fields_order"):
            return None
        return cls.Meta.form_fields_order
