"""
Handler parameter sources.

A handler declares where each Pydantic model comes from with a marker:

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    async def create(
        self,
        req: Request,
        data: RequestBody[CreateUser],
        query_data: QueryParams[UserQuery],
    ) -> Response[UserOut]: ...

``RequestBody[M]`` is built from the request body (read as the @consumes
media type says) and ``QueryParams[M]`` from the query string. Both are
``Annotated`` aliases, so type checkers see a plain ``M``.

The controller resolves a handler's parameters once (the plan is cached per
function) and injects them on every request.
"""

from dataclasses import dataclass, field
import inspect
from typing import (
    Annotated,
    Any,
    Callable,
    Mapping,
    Optional,
    Type,
    TypeAlias,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)
from weakref import WeakKeyDictionary

from pydantic import BaseModel

from ..exceptions import UnexpectedDecorator

ModelT = TypeVar("ModelT", bound=BaseModel)


class ParamSource:
    """Base marker for a parameter source (``Annotated`` metadata)."""

    #: Name used in validation error locations and documentation.
    location: str = ""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class BodySource(ParamSource):
    """The request body, read as the endpoint's @consumes media type."""

    location = "body"


class QuerySource(ParamSource):
    """The query string."""

    location = "query"


RequestBody: TypeAlias = Annotated[ModelT, BodySource()]
"""``RequestBody[M]``: the model is built from the request body."""

QueryParams: TypeAlias = Annotated[ModelT, QuerySource()]
"""``QueryParams[M]``: the model is built from the query parameters."""


@dataclass(frozen=True)
class SourcedParam:
    """A handler parameter with a declared source."""

    name: str
    model: Type[BaseModel]
    source: ParamSource


@dataclass(frozen=True)
class HandlerParams:
    """Where a handler's model parameters come from."""

    body: Optional[SourcedParam] = None
    query: tuple[SourcedParam, ...] = ()
    #: Pydantic-model parameters without a source marker.
    unmarked: tuple[tuple[str, Type[BaseModel]], ...] = field(default=())


_PLANS: "WeakKeyDictionary[Callable[..., Any], HandlerParams]" = WeakKeyDictionary()


def _underlying(func: Callable[..., Any]) -> Callable[..., Any]:
    """The plain function behind bound methods and decorator wrappers."""
    while True:
        func = getattr(func, "__func__", func)
        wrapped = getattr(func, "__wrapped__", None)
        if wrapped is None:
            return func
        func = wrapped


def _is_model(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _split_annotation(tp: Any) -> tuple[Any, Optional[ParamSource]]:
    """(type, source) for ``Annotated[T, ..., Source(), ...]``; (tp, None) otherwise."""
    if get_origin(tp) is not Annotated:
        return tp, None
    inner, *metadata = get_args(tp)
    sources = [m for m in metadata if isinstance(m, ParamSource)]
    if len(sources) > 1:
        raise TypeError("A parameter can only have one source marker.")
    return inner, (sources[0] if sources else None)


def _parameter_hints(func: Callable[..., Any], qualname: str) -> dict[str, Any]:
    """
    The handler's resolved annotations. If some cannot be resolved (a name
    imported only for type checking, say), the others are resolved one by
    one; an unresolvable RequestBody/QueryParams annotation is an error,
    since the parameter could not be injected.
    """
    try:
        return get_type_hints(func, include_extras=True)
    # pylint: disable-next=W0718
    except Exception:
        pass

    hints: dict[str, Any] = {}
    namespace = getattr(func, "__globals__", {})
    for name, annotation in (getattr(func, "__annotations__", {}) or {}).items():
        if not isinstance(annotation, str):
            hints[name] = annotation
            continue
        try:
            # pylint: disable-next=W0123
            hints[name] = eval(annotation, namespace)  # noqa: S307 - annotation
        # pylint: disable-next=W0718
        except Exception as exc:
            if "RequestBody" in annotation or "QueryParams" in annotation:
                raise TypeError(
                    f"{qualname}: cannot resolve the annotation {annotation!r} "
                    f"of parameter {name!r}: {exc}"
                ) from exc
            hints[name] = annotation
    return hints


def handler_params(func: Callable[..., Any]) -> HandlerParams:
    """
    Returns (and caches) the parameter plan of a handler. The first two
    parameters (``self`` and ``req``) are skipped for plain functions; a
    bound method skips ``req`` only.

    Raises TypeError when a marker wraps something other than a Pydantic
    model, or when a handler declares more than one RequestBody.
    """
    target = _underlying(func)
    try:
        return _PLANS[target]
    except (KeyError, TypeError):
        pass

    plan = _build_plan(target)
    try:
        _PLANS[target] = plan
    except TypeError:  # pragma: no cover - not weak-referenceable
        pass
    return plan


def _build_plan(func: Callable[..., Any]) -> HandlerParams:
    # Parameters: [0]=self, [1]=req, others start at index 2
    parameters = list(inspect.signature(func).parameters.values())[2:]
    qualname = getattr(func, "__qualname__", repr(func))
    hints = _parameter_hints(func, qualname)

    body: Optional[SourcedParam] = None
    query: list[SourcedParam] = []
    unmarked: list[tuple[str, Type[BaseModel]]] = []

    for param in parameters:
        annotation = hints.get(param.name, param.annotation)
        inner, source = _split_annotation(annotation)
        if source is None:
            if _is_model(inner):
                unmarked.append((param.name, inner))
            continue
        if not _is_model(inner):
            raise TypeError(
                f"{qualname}: parameter {param.name!r} is marked as "
                f"{type(source).__name__} but {inner!r} is not a Pydantic model."
            )
        sourced = SourcedParam(param.name, inner, source)
        if isinstance(source, BodySource):
            if body is not None:
                raise TypeError(
                    f"{qualname}: parameters {body.name!r} and {param.name!r} are "
                    "both RequestBody. A request has one body; use one model."
                )
            body = sourced
        elif isinstance(source, QuerySource):
            query.append(sourced)

    return HandlerParams(body=body, query=tuple(query), unmarked=tuple(unmarked))


def check_endpoint_params(
    func: Callable[..., Any], handler_info: Mapping[str, Any]
) -> HandlerParams:
    """
    Validates a handler's parameters against its endpoint configuration when
    the controller is registered, so mistakes fail at startup instead of on
    the first request.
    """
    plan = handler_params(func)
    qualname = getattr(_underlying(func), "__qualname__", repr(func))
    http_method = str(handler_info.get("http_method", "")).upper()
    consumes = handler_info.get("consumes")

    if plan.unmarked:
        name, model = plan.unmarked[0]
        raise TypeError(
            f"{qualname}: parameter {name!r} is a Pydantic model without a "
            f"source. Annotate it as RequestBody[{model.__name__}] or "
            f"QueryParams[{model.__name__}]."
        )
    if http_method == "GET" and consumes:
        raise UnexpectedDecorator("GET endpoints can't consume request bodies.")
    if plan.body is not None and not consumes:
        raise TypeError(
            f"{qualname}: parameter {plan.body.name!r} is a RequestBody, but the "
            "endpoint has no @consumes(...) saying how to read the body."
        )
    return plan
