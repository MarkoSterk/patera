"""
Typed values from the Admin record forms.

A browser form sends every value as text: "31" for a number, "true" for a
ticked checkbox and nothing at all for an unticked one. Models without a
validation schema of their own get their form converted here, from the
column types: only the fields the form shows are kept, each value is
converted to the column's Python type, and an unticked checkbox is False.
Record keys in Admin URLs are converted the same way.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional, Type

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.inspection import inspect

from patera.database.sql import DeclarativeBaseModel

TRUE_VALUES = frozenset({"true", "on", "1", "yes"})


class AdminFormError(ValueError):
    """Form values that do not fit their fields; ``errors`` lists them."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("Invalid record data.")
        self.errors = errors


def _python_type(model: Type[DeclarativeBaseModel], field: dict[str, Any]) -> Any:
    """The Python type of a form field, or None when it cannot be told."""
    if not field.get("is_column", True):
        return model.add_to_form().get(field["name"])
    column = inspect(model).columns[field["name"]]
    try:
        return column.type.python_type
    except NotImplementedError:
        return None


def _nullable(model: Type[DeclarativeBaseModel], field: dict[str, Any]) -> bool:
    if not field.get("is_column", True):
        return True
    return bool(inspect(model).columns[field["name"]].nullable)


def convert_value(python_type: Any, value: Any) -> Any:
    """Converts one submitted value to ``python_type``. Raises ValueError."""
    if python_type is None or not isinstance(value, str):
        return value
    if python_type is bool:
        return value.strip().lower() in TRUE_VALUES
    if isinstance(python_type, type) and issubclass(python_type, Enum):
        try:
            return python_type(value)
        except ValueError:
            try:
                return python_type[value]
            except KeyError:
                raise ValueError(f"{value!r} is not one of the choices") from None
    try:
        return TypeAdapter(python_type).validate_python(value)
    except ValidationError as exc:
        raise ValueError(exc.errors()[0]["msg"]) from None


def form_values(
    model: Type[DeclarativeBaseModel],
    fields: list[dict[str, Any]],
    data: Mapping[str, Any],
    *,
    creating: bool,
) -> dict[str, Any]:
    """
    The values of the submitted form, converted for ``model``.

    - Only fields in ``fields`` (the form's fields) are kept; anything else
      in the request is ignored, so hidden fields cannot be set.
    - A checkbox that was not sent is False.
    - An empty value of a non-text field is None for a nullable column and
      left out otherwise (the column default applies on create).
    - On create, a required field without a value is an error.
    - Custom form fields keep the value their element sends, unless the
      element sets ``converts_value`` (DateInput), which converts it like a
      generated input.

    Raises AdminFormError listing every field that does not fit.
    """
    values: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for field in fields:
        name = field["name"]
        python_type = _python_type(model, field)
        custom_field = field.get("custom_field")
        if custom_field is not None and not getattr(
            custom_field, "converts_value", False
        ):
            if name in data:
                values[name] = data[name]
            continue
        if python_type is bool:
            values[name] = convert_value(bool, data.get(name, "false"))
            continue
        if name not in data:
            if creating and field.get("required"):
                errors.append(_error(name, "Field required", "missing"))
            continue
        value = data[name]
        if isinstance(value, str) and value.strip() == "" and python_type is not str:
            if _nullable(model, field):
                values[name] = None
            elif creating and field.get("required"):
                errors.append(_error(name, "Field required", "missing"))
            continue
        try:
            values[name] = convert_value(python_type, value)
        except ValueError as exc:
            errors.append(_error(name, str(exc), "invalid"))
    if errors:
        raise AdminFormError(errors)
    return values


def primary_key_values(
    model: Type[DeclarativeBaseModel], pk_values: Mapping[str, str]
) -> Optional[dict[str, Any]]:
    """
    The record key from an Admin URL, converted to the key columns' types,
    or None when it names other columns or does not fit them.
    """
    columns = {column.key: column for column in inspect(model).primary_key}
    if set(pk_values) != set(columns):
        return None
    converted: dict[str, Any] = {}
    for name, value in pk_values.items():
        try:
            python_type = columns[name].type.python_type
        except NotImplementedError:
            python_type = None
        try:
            converted[name] = convert_value(python_type, value)
        except ValueError:
            return None
    return converted


def _error(name: str, message: str, kind: str) -> dict[str, Any]:
    return {"loc": [name], "msg": message, "type": kind}
