from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Type, cast

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.inspection import inspect

from patera import Patera, Request, Response, MediaType, HttpStatus
from patera.controller import Controller, get, post, consumes
from patera.database.sql import DeclarativeBaseModel, SqlDatabase
from patera.auth import role_required

from .admin_interface import AdminInterface, Permissions
from .exceptions import UnknownModelException, UnknownDatabaseException


class _AdminDbController(Controller[Patera]):
    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @get("/<string:db_name>")
    @role_required(Permissions.ADMIN_CAN_VIEW)
    async def database_overview(self, req: Request, db_name: str) -> Response:
        """
        Database overview page.
        """
        db: Optional[SqlDatabase] = self.app.extensions.get(db_name, None)

        if db is None:
            raise UnknownDatabaseException(db_name)

        db_models = [
            model
            for model in self.admin_interface.managed_models
            if model.__db_name__ == db_name
        ]

        overview = await db.collect_db_overview()

        return await req.res.html(
            "_admin/databases/db_overview.html",
            {
                **self.admin_interface.context_variables,
                "db_overview": overview,
                "db_tables": db_models,
                "db": db,
            },
        )

    @get("/<string:db_name>/model/<string:model_name>")
    @role_required(Permissions.ADMIN_CAN_VIEW)
    async def get_list(self, req: Request, db_name: str, model_name: str) -> Response:
        """
        Gets paginated list of model records.
        """
        db: Optional[SqlDatabase] = self.app.extensions.get(db_name, None)

        if db is None:
            raise UnknownDatabaseException(db_name)

        model: Type[DeclarativeBaseModel] = self.get_model(model_name, db_name)

        page = self.get_positive_int_query_param(req, "page", 1)
        count = self.get_positive_int_query_param(req, "count", 10)

        async with db.create_session() as session:
            records = await model.query(session).paginate(
                page=page,
                per_page=count,
            )

        table_columns = self.get_admin_table_columns(model)
        create_fields = self.get_admin_create_form_fields(model)

        return await req.res.html(
            "_admin/databases/db_records_table.html",
            {
                **self.admin_interface.context_variables,
                "db_name": db_name,
                "model_name": model_name,
                "table_name": model.__tablename__,
                "records": records,
                "table_columns": table_columns,
                "create_fields": create_fields,
                "pagination_pages": self.get_pagination_pages(
                    records.page,
                    records.pages,
                ),
                "get_record_value": self.get_record_value,
                "get_record_primary_key_value": self.get_record_primary_key_value,
                "render_custom_form_field": self.render_custom_form_field,
                "model": model,
                "db": db,
            },
        )

    @post("/<string:db_name>/model/<string:model_name>/create")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @role_required(Permissions.ADMIN_CAN_CREATE)
    async def create_record(
        self,
        req: Request,
        db_name: str,
        model_name: str,
    ) -> Response:
        """
        Creates a new database record from the admin create form.
        """
        try:
            db: SqlDatabase = self.get_db(db_name)
            model: Type[DeclarativeBaseModel] = self.get_model(model_name, db_name)
            validation_schema: Optional[Type[BaseModel]] = (
                model.create_validation_schema()
            )

            form_data = await req.form_and_files()
            if validation_schema:
                form_data = validation_schema.model_validate(form_data).model_dump()

            async with db.create_session() as session:
                async with session.begin():
                    record = model()
                    await record.admin_create(form_data)
                    session.add(record)

            return req.res.redirect(
                self.admin_interface.url_for(
                    "_AdminDbController.get_list",
                    db_name=db_name,
                    model_name=model_name,
                )
            )
        except Exception as e:
            self.app.logger.exception(e)
            return req.res.json(
                {
                    "message": f"Failed to create record in database {db_name} and table {model_name}",
                    "status": "error",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)

    def get_positive_int_query_param(
        self,
        req: Request,
        name: str,
        default: int,
    ) -> int:
        """
        Reads a positive integer query parameter.
        Falls back to default if the value is missing or invalid.
        """
        raw_value = req.query_parameters.get(name, default)

        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return default

        return max(value, 1)

    def get_pagination_pages(
        self,
        current_page: int,
        total_pages: int,
        window: int = 2,
    ) -> list[int]:
        """
        Returns a small page window around the current page.

        Example:
        current_page=5, total_pages=10 -> [3, 4, 5, 6, 7]
        """
        if total_pages <= 0:
            return []

        start = max(current_page - window, 1)
        end = min(current_page + window, total_pages)

        return list(range(start, end + 1))

    def get_db(self, db_name) -> SqlDatabase:
        db: Optional[SqlDatabase] = self.app.extensions.get(db_name, None)
        if db is None:
            raise UnknownDatabaseException(db_name)
        return db

    def get_model(
        self,
        model_name: str,
        db_name: str,
    ) -> Type[DeclarativeBaseModel]:
        """
        Gets a managed model by model name and database name.
        """
        for model in self.admin_interface.managed_models:
            if (
                model.__name__.lower() == model_name.lower()
                and model.__db_name__.lower() == db_name.lower()
            ):
                return model

        raise UnknownModelException(model_name, db_name)

    def get_admin_table_columns(
        self,
        model: Type[DeclarativeBaseModel],
    ) -> list[dict[str, str]]:
        """
        Returns table columns for the admin list view.

        Uses:
        - model.Meta.exclude_from_table
        - model.Meta.form_fields_order
        - model.Meta.custom_labels
        """
        mapper = inspect(model)

        model_columns: list[str] = [column.key for column in mapper.columns]

        excluded_columns = set(model.exclude_from_table())
        labels_map = model.form_labels_map()
        preferred_order = model.form_fields_order() or []

        visible_columns = [
            column_name
            for column_name in model_columns
            if column_name not in excluded_columns
        ]

        ordered_columns = self.order_field_names(
            available_field_names=visible_columns,
            preferred_order=preferred_order,
        )

        return [
            {
                "name": column_name,
                "label": labels_map.get(
                    column_name,
                    column_name.replace("_", " ").title(),
                ),
            }
            for column_name in ordered_columns
        ]

    def get_admin_create_form_fields(
        self,
        model: Type[DeclarativeBaseModel],
    ) -> list[dict[str, Any]]:
        """
        Returns create-form field metadata for the admin create dialog.

        Uses:
        - model.Meta.exclude_from_create_form
        - model.Meta.form_fields_order
        - model.Meta.custom_labels
        - model.Meta.custom_form_fields
        - model.Meta.add_to_form

        Primary keys are always excluded because they are generated by the database.
        """
        mapper = inspect(model)

        excluded_fields = set(model.exclude_from_create_form())
        excluded_fields.update(
            pk_name for pk_name in (model.primary_key_names() or []) if pk_name
        )

        labels_map = model.form_labels_map()
        preferred_order = model.form_fields_order() or []
        custom_form_fields = model.custom_form_fields()
        additional_fields = model.add_to_form()

        fields: dict[str, dict[str, Any]] = {}

        for column in mapper.columns:
            field_name = column.key

            if field_name in excluded_fields:
                continue

            fields[field_name] = {
                "name": field_name,
                "label": labels_map.get(
                    field_name,
                    field_name.replace("_", " ").title(),
                ),
                "input_type": self.get_input_type_for_column(column),
                "required": self.is_required_column(column),
                "custom_field": custom_form_fields.get(field_name),
                "choices": self.get_column_choices(column),
                "is_column": True,
            }

        for field_name, field_type in additional_fields.items():
            if field_name in excluded_fields:
                continue

            fields[field_name] = {
                "name": field_name,
                "label": labels_map.get(
                    field_name,
                    field_name.replace("_", " ").title(),
                ),
                "input_type": self.get_input_type_for_python_type(field_type),
                "required": False,
                "custom_field": custom_form_fields.get(field_name),
                "choices": self.get_python_type_choices(field_type),
                "is_column": False,
            }

        ordered_field_names = self.order_field_names(
            available_field_names=list(fields.keys()),
            preferred_order=preferred_order,
        )

        return [fields[field_name] for field_name in ordered_field_names]

    def order_field_names(
        self,
        available_field_names: list[str],
        preferred_order: list[str],
    ) -> list[str]:
        """
        Orders fields using preferred_order first, then appends the remaining fields.
        """
        ordered_field_names: list[str] = []

        for field_name in preferred_order:
            if (
                field_name in available_field_names
                and field_name not in ordered_field_names
            ):
                ordered_field_names.append(field_name)

        for field_name in available_field_names:
            if field_name not in ordered_field_names:
                ordered_field_names.append(field_name)

        return ordered_field_names

    def is_required_column(self, column: Any) -> bool:
        """
        Determines whether a column should be marked as required in the create form.
        """
        if column.primary_key and column.autoincrement:
            return False

        if column.nullable:
            return False

        if column.default is not None:
            return False

        if column.server_default is not None:
            return False

        return True

    def get_input_type_for_column(self, column: Any) -> str:
        """
        Maps SQLAlchemy column types to admin form input types.
        """
        column_type = column.type

        if isinstance(column_type, Boolean):
            return "checkbox"

        if isinstance(column_type, Integer):
            return "number"

        if isinstance(column_type, Float) or isinstance(column_type, Numeric):
            return "number-decimal"

        if isinstance(column_type, DateTime):
            return "datetime-local"

        if isinstance(column_type, Date):
            return "date"

        if isinstance(column_type, Text):
            return "textarea"

        if isinstance(column_type, SqlEnum):
            return "select"

        if isinstance(column_type, String):
            return "text"

        return "text"

    def get_input_type_for_python_type(self, python_type: type[Any]) -> str:
        """
        Maps Python types from Meta.add_to_form to admin form input types.
        """
        if python_type is bool:
            return "checkbox"

        if python_type is int:
            return "number"

        if python_type is float or python_type is Decimal:
            return "number-decimal"

        if python_type is date:
            return "date"

        if python_type is datetime:
            return "datetime-local"

        if isinstance(python_type, type) and issubclass(python_type, Enum):
            return "select"

        return "text"

    def get_column_choices(self, column: Any) -> list[dict[str, str]]:
        """
        Extracts select choices from SQLAlchemy Enum columns.
        """
        column_type = column.type

        if not isinstance(column_type, SqlEnum):
            return []

        return [
            {
                "value": str(value),
                "label": str(value).replace("_", " ").title(),
            }
            for value in column_type.enums
        ]

    def get_python_type_choices(
        self,
        python_type: type[Any],
    ) -> list[dict[str, str]]:
        """
        Extracts select choices from Python Enum types used in Meta.add_to_form.
        """
        if not isinstance(python_type, type):
            return []

        if not issubclass(python_type, Enum):
            return []

        return [
            {
                "value": str(choice.value),
                "label": choice.name.replace("_", " ").title(),
            }
            for choice in python_type
        ]

    def render_custom_form_field(self, field: dict[str, Any]) -> str:
        """
        Renders a custom form field, if the field defines one.

        This method supports a few common render APIs:
        - field.render(field_metadata)
        - field.markup(field_metadata)
        - field.html(field_metadata)

        Adjust this method if your custom field classes use a different API.
        """
        custom_field = field.get("custom_field")

        if custom_field is None:
            return ""

        if hasattr(custom_field, "render"):
            return custom_field.render(field)

        if hasattr(custom_field, "markup"):
            return custom_field.markup(field)

        if hasattr(custom_field, "html"):
            return custom_field.html(field)

        return ""

    def get_record_value(
        self,
        record: DeclarativeBaseModel,
        column_name: str,
    ) -> Any:
        """
        Safely gets a value from an ORM record.
        """
        value = getattr(record, column_name, "")

        if value is None:
            return ""

        return value

    def get_record_primary_key_value(
        self,
        record: DeclarativeBaseModel,
        model: Type[DeclarativeBaseModel],
    ) -> str:
        """
        Returns a string representation of the primary key value.

        Supports single-column and composite primary keys.
        """
        pk_names = model.primary_key_names() or []

        values = [
            str(getattr(record, pk_name)) for pk_name in pk_names if pk_name is not None
        ]

        return "|".join(values)

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
