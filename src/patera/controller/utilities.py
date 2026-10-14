"""
Utility methods for controller related things
"""

from collections.abc import Collection
from types import NoneType, UnionType
from typing import (
    Any,
    Annotated,
    Type,
    Union,
    get_origin,
    get_args,
    Mapping,
)
import inspect
from pydantic import BaseModel, ValidationError

from ..exceptions.http_exceptions import RequestValidationError

from ..request import Request
from ..media_types import MediaType


def _unwrap_annotated(tp: Any) -> Any:
    """If Annotated[T, ...], return T; else the original."""
    if get_origin(tp) is Annotated:
        args = get_args(tp)
        return args[0] if args else tp
    return tp


def _is_subclass(x: Any, base: Type) -> bool:
    try:
        return inspect.isclass(x) and issubclass(x, base)
    except Exception:
        return False


def _is_pydantic_model(tp: Any) -> bool:
    return _is_subclass(tp, BaseModel)


def _is_collection_type(annotation: Any) -> bool:
    """True for list[str], set[int], tuple[str, ...], Optional[list[str]], ..."""
    annotation = _unwrap_annotated(annotation)
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return any(
            _is_collection_type(arg)
            for arg in get_args(annotation)
            if arg is not NoneType
        )
    target = origin or annotation
    return (
        inspect.isclass(target)
        and issubclass(target, Collection)
        and not issubclass(target, (str, bytes, bytearray, Mapping))
    )


def _form_values_for_model(
    model_cls: Type[BaseModel], data: Mapping[str, Any]
) -> dict[str, Any]:
    """
    A form sends a field once per value, so a multi-select with one option
    chosen arrives as a single value. Fields the model declares as lists
    (or sets, tuples) get that value wrapped in a list.
    """
    values = dict(data)
    for name, field in model_cls.model_fields.items():
        if not _is_collection_type(field.annotation):
            continue
        for key in {name, field.alias, field.validation_alias}:
            if isinstance(key, str) and key in values:
                if not isinstance(values[key], list):
                    values[key] = [values[key]]
    return values


def _build_model(
    model_cls: Type[BaseModel],
    data: Any,
    media_type: "MediaType | None" = None,
) -> BaseModel:
    """
    Builds the @consumes model from the request data. Invalid data raises
    RequestValidationError (422).
    """
    if media_type in (
        MediaType.APPLICATION_X_WWW_FORM_URLENCODED,
        MediaType.MULTIPART_FORM_DATA,
    ) and isinstance(data, Mapping):
        data = _form_values_for_model(model_cls, data)
    try:
        return model_cls.model_validate(data)  # type: ignore[attr-defined]
    except ValidationError as exc:
        raise RequestValidationError(exc) from exc


def _content_type_matches(incoming: str, expected: "MediaType") -> bool:
    """
    Accept parameters (e.g., '; charset=utf-8') and handle +json suffixes.
    """
    inc = (incoming or "").lower()
    exp = expected.value.lower()
    base = inc.split(";")[0].strip()

    if exp == MediaType.APPLICATION_JSON.value:
        # RFC 6839: */*+json is valid too
        return base == "application/json" or base.endswith("+json")
    if exp == MediaType.APPLICATION_PROBLEM_JSON.value:
        # RFC 7807; accept application/problem+json and */*+json
        return base in (
            "application/problem+json",
            "application/json",
        ) or base.endswith("+json")
    if exp == MediaType.MULTIPART_FORM_DATA.value:
        return base == "multipart/form-data"
    if exp == MediaType.APPLICATION_X_WWW_FORM_URLENCODED.value:
        return base == "application/x-www-form-urlencoded"
    return base == exp


async def _read_payload_for_consumes(
    req: "Request", mt: "MediaType"
) -> Mapping[str, Any]:
    """
    Map declared MediaType → Request loader.
    Returns mapping suitable for building Pydantic models. An empty JSON
    body becomes an empty mapping; malformed JSON raises InvalidRequestBody
    (400), and a body over the size limit raises RequestBodyTooLarge (413).
    """
    if mt in (MediaType.APPLICATION_JSON, MediaType.APPLICATION_PROBLEM_JSON):
        return (await req.json()) or {}
    if mt == MediaType.APPLICATION_X_WWW_FORM_URLENCODED:
        return await req.form()
    if mt == MediaType.MULTIPART_FORM_DATA:
        return await req.form_and_files()
    # extend with additional types if needed.
    return {}
