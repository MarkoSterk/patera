# base_protocol.py
# pylint: disable=W0613

from __future__ import annotations
from typing import Any, Optional, Tuple, cast, Type, Protocol
from pydantic import BaseModel

from sqlalchemy import Column
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession
from .sqlalchemy_async_query import AsyncQuery

from patera import Request


class MetaProtocol(Protocol):
    exclude_from_create_form: list[str]
    exclude_from_update_form: list[str]
    exclude_from_table: list[str]

    add_to_form: dict[str, Type]

    custom_labels: dict[str, str]
    custom_form_fields: list[Type]

    form_fields_order: list[str]

    create_validation_shema: Type[BaseModel]
    update_validation_shema: Type[BaseModel]


class DeclarativeBaseModel(DeclarativeBase):
    """
    Defines the interface that the custom
    DeclarativeBase class must satisfy.
    """

    __db_name__: str
    __db_configs_name__: str
    __abstract__ = True

    class Meta(MetaProtocol):
        exclude_from_create_form: list[str]
        exclude_from_update_form: list[str]
        exclude_from_table: list[str]

        add_to_form: dict[str, Type]

        custom_labels: dict[str, str]
        custom_form_fields: list[Type]

        form_fields_order: list[str]

        create_validation_shema: Type[BaseModel]
        update_validation_shema: Type[BaseModel]

    def __init__(self, **kwargs):
        if kwargs is not None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__abstract__:
            if "__db_name__" not in cls.__dict__:
                raise TypeError(
                    f"{cls.__name__} must define a class attribute '__db_name__'"
                )

    async def admin_create(
        self, req: "Request", new_data: dict[str, Any], session: "AsyncSession"
    ) -> None:
        """
        Saves the current instance to the database. Used in admin dashboard forms
        for creating and editing records. If customization is needed, override this method
        in the model class.
        """
        for key, value in new_data.items():
            setattr(self, key, value)
        session.add(self)

    async def admin_delete(self, req: "Request", session: "AsyncSession") -> None:
        """
        Deletes the current instance from the database. Used in admin dashboard
        for deleting records. If customization is needed, override this method
        in the model class.
        """
        await session.delete(self)

    async def admin_update(
        self, req: "Request", new_data: dict[str, Any], session: "AsyncSession"
    ) -> None:
        """
        Updates the current instance with new data. Used in admin dashboard
        forms for editing records. If customization is needed, override this method
        in the model class.
        """
        for key, value in new_data.items():
            setattr(self, key, value)
        session.add(self)

    @classmethod
    def query(cls, session: AsyncSession) -> AsyncQuery:
        return AsyncQuery(session, cls)

    @classmethod
    def db_name(cls) -> str:
        return cls.__db_name__

    @classmethod
    def db_configs_name(cls) -> str:
        return cls.__db_configs_name__

    @classmethod
    def primary_key_names(cls) -> Optional[list[str]]:
        """
        Returns the attribute names of the primary key columns.
        """
        mapper = inspect(cls)
        pks = mapper.primary_key

        if not pks:
            return None

        return [pk.key for pk in pks]  # pks[0].key

    @classmethod
    def primary_keys(cls) -> Optional[Tuple[Column[Any]]]:
        mapper = inspect(cls)
        pks = mapper.primary_key
        if not pks:
            return None
        return cast(Tuple[Column[Any]], pks)

    @classmethod
    def exclude_from_create_form(cls) -> list[str]:
        """Returns all fields that are declared as hidden in the form"""
        if not hasattr(cls.Meta, "exclude_from_create_form"):
            return []
        return cls.Meta.exclude_from_create_form

    @classmethod
    def exclude_from_update_form(cls) -> list[str]:
        """Returns all fields that are declared as hidden in the form"""
        if not hasattr(cls.Meta, "exclude_from_update_form"):
            return []
        return cls.Meta.exclude_from_update_form

    @classmethod
    def exclude_from_table(cls) -> list[str]:
        """Returns all fields that are declared as excluded in the table"""
        if not hasattr(cls.Meta, "exclude_from_table"):
            return []
        return cls.Meta.exclude_from_table

    @classmethod
    def form_labels_map(cls) -> dict[str, str]:
        """Map of attribute names -> human readable names"""
        if not hasattr(cls.Meta, "custom_labels"):
            return {}
        return cls.Meta.custom_labels

    @classmethod
    def custom_form_fields(cls) -> dict[str, Type]:
        """Returns custom form fields for the admin dashboard forms"""
        if not hasattr(cls.Meta, "custom_form_fields"):
            return {}
        return {input.id: input for input in cls.Meta.custom_form_fields}

    @classmethod
    def add_to_form(cls) -> dict[str, Any]:
        """Returns additional form fields to be added to admin dashboard forms"""
        if not hasattr(cls.Meta, "add_to_form"):
            return {}
        return cls.Meta.add_to_form

    @classmethod
    def create_validation_schema(cls) -> Optional[Type[BaseModel]]:
        """Returns the schema used for validating creation forms in admin dashboard"""
        if not hasattr(cls.Meta, "create_validation_shema"):
            return None
        return cls.Meta.create_validation_shema

    @classmethod
    def update_validation_schema(cls) -> Optional[Type[BaseModel]]:
        """Returns the schema used for validating edit forms in admin dashboard"""
        if not hasattr(cls.Meta, "update_validation_shema"):
            return None
        return cls.Meta.update_validation_shema

    @classmethod
    def order_table_by(cls) -> Optional[list[str]]:
        """Returns list of strings used for ordering the table in admin dashboard"""
        if not hasattr(cls.Meta, "order_table_by"):
            return None
        return cls.Meta.order_table_by

    @classmethod
    def form_fields_order(cls) -> Optional[list[str]]:
        """
        Returns a list of string with the order of input fields or None
        """
        if not hasattr(cls.Meta, "form_fields_order"):
            return None
        return cls.Meta.form_fields_order
