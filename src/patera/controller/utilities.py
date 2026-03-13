"""
Utility methods for controller related things
"""

from typing import (
    Any,
    Annotated,
    Type,
    Optional,
    get_origin,
    get_args,
    Mapping,
    get_type_hints,
)
import inspect
from pydantic import BaseModel

from ..request import Request
from ..response import Response
from ..media_types import MediaType


def _get_handler_dict(obj: Any) -> dict[str, Any]:
    """Return or create the _handler dict on an object."""
    d = getattr(obj, "_handler", None)
    if not isinstance(d, dict):
        d = {}
        setattr(obj, "_handler", d)
    return d


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


def _build_model(model_cls: Type[BaseModel], data: Any) -> BaseModel:
    return model_cls.model_validate(data)  # type: ignore[attr-defined]


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
    Returns mapping suitable for building Pydantic models.
    """
    if mt in (MediaType.APPLICATION_JSON, MediaType.APPLICATION_PROBLEM_JSON):
        return (await req.json()) or {}
    if mt == MediaType.APPLICATION_X_WWW_FORM_URLENCODED:
        return await req.form()
    if mt == MediaType.MULTIPART_FORM_DATA:
        return await req.form_and_files()
    # extend with additional types if needed.
    return {}


def _extract_response_type(func) -> Optional[Type[Any]]:
    """
    If the function is annotated as -> Response[T], return T; else None.
    """
    hints = get_type_hints(func, include_extras=True)
    ret = hints.get("return")
    if ret is None:
        return None
    if get_origin(ret) is Response:
        args = get_args(ret)
        if args:
            t = args[0]
            if get_origin(t) is Annotated:  # peel Annotated[T, ...]
                t = get_args(t)[0]
            return t
    return None
