"""
Handler parameter sources.

A handler declares where its input comes from with a marker:

    @post("/")
    @consumes(MediaType.APPLICATION_JSON)
    async def create(
        self,
        req: Request,
        data: RequestBody[CreateUser],
        query_data: QueryParams[UserQuery],
    ) -> Response[UserOut]: ...

``RequestBody[T]`` is built from the request body, read as the @consumes
media type says. ``T`` is a Pydantic model, or for JSON bodies any type
Pydantic validates, such as ``list[CreateUser]``. ``QueryParams[M]`` builds
a model from the query string. ``Files[...]`` takes the files a multipart
body sent under the parameter's name:

    @post("/profile")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    async def update(
        self,
        req: Request,
        data: RequestBody[ProfileForm],
        avatar: Files[UploadedFile],
        attachments: Files[list[UploadedFile]],
    ) -> Response: ...

``Headers[M]`` and ``Cookies[M]`` build a model from request headers and
cookies. A header field ``x_request_id`` reads the header ``X-Request-Id``
(underscores become hyphens, case is ignored); a cookie field reads the
cookie of the same name. A field alias gives any other name:

    class ClientHeaders(BaseModel):
        user_agent: str
        client_ip: str = Field(alias="X-Forwarded-For")

All markers are ``Annotated`` aliases, so type checkers see a plain ``T``.

The controller resolves a handler's parameters once (the plan is cached per
function) and injects them on every request.
"""

from dataclasses import dataclass, field
import inspect
from types import NoneType, UnionType
from typing import (
    Annotated,
    Any,
    Callable,
    Mapping,
    Optional,
    Type,
    TypeAlias,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)
from weakref import WeakKeyDictionary

from pydantic import BaseModel, Field, TypeAdapter, create_model

from ..exceptions import UnexpectedDecorator
from ..media_types import MediaType
from ..request import UploadedFile

T = TypeVar("T")
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


class FileSource(ParamSource):
    """Files of a multipart body, under the parameter's name."""

    location = "files"


RequestBody: TypeAlias = Annotated[T, BodySource()]
"""``RequestBody[T]``: the value is built from the request body."""

QueryParams: TypeAlias = Annotated[ModelT, QuerySource()]
"""``QueryParams[M]``: the model is built from the query parameters."""


class HeaderSource(ParamSource):
    """Request headers, matched by name without regard to case."""

    location = "header"


class CookieSource(ParamSource):
    """Request cookies, matched by exact name."""

    location = "cookie"


Headers: TypeAlias = Annotated[ModelT, HeaderSource()]
"""``Headers[M]``: the model is built from the request headers."""

Cookies: TypeAlias = Annotated[ModelT, CookieSource()]
"""``Cookies[M]``: the model is built from the request cookies."""

Files: TypeAlias = Annotated[T, FileSource()]
"""
``Files[UploadedFile]``, ``Files[list[UploadedFile]]`` (either optional with
``| None`` or a default), ``Files[Model]`` with file fields (validated like
any model), or ``Files[dict[str, list[UploadedFile]]]`` for every file of
the request by field name.
"""

_FORM_MEDIA_TYPES = (
    MediaType.APPLICATION_X_WWW_FORM_URLENCODED,
    MediaType.MULTIPART_FORM_DATA,
)


@dataclass(frozen=True)
class SourcedParam:
    """A handler parameter with a declared source."""

    name: str
    #: The declared type: a Pydantic model, or any type for a JSON body.
    model: Any
    source: ParamSource
    #: Validates a body that is not a Pydantic model (``list[Model]``, ...).
    adapter: Optional[TypeAdapter[Any]] = field(default=None, compare=False)
    #: Headers/Cookies: (model input key, HTTP name, list field) per field.
    names: tuple[tuple[str, str, bool], ...] = ()

    @property
    def is_model(self) -> bool:
        return _is_model(self.model)


@dataclass(frozen=True)
class HandlerParams:
    """Where a handler's parameters come from."""

    body: Optional[SourcedParam] = None
    query: tuple[SourcedParam, ...] = ()
    headers: tuple[SourcedParam, ...] = ()
    cookies: tuple[SourcedParam, ...] = ()
    #: Files[...] parameters bound to the file field of the same name.
    files: tuple[SourcedParam, ...] = ()
    #: Validates the named file fields together (one field per parameter).
    files_model: Optional[Type[BaseModel]] = None
    #: Files[Model] parameters, each built from the files its fields name.
    file_models: tuple[SourcedParam, ...] = ()
    #: The Files[dict[str, list[UploadedFile]]] parameter, if any.
    all_files: Optional[str] = None
    #: Pydantic-model parameters without a source marker.
    unmarked: tuple[tuple[str, Type[BaseModel]], ...] = ()

    @property
    def has_sources(self) -> bool:
        return bool(
            self.body is not None
            or self.query
            or self.headers
            or self.cookies
            or self.reads_files
        )

    @property
    def reads_files(self) -> bool:
        return bool(self.files or self.file_models or self.all_files)

    @property
    def file_param_names(self) -> list[str]:
        names = [p.name for p in (*self.files, *self.file_models)]
        return names + ([self.all_files] if self.all_files else [])


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


def _strip_optional(tp: Any) -> tuple[Any, bool]:
    """(T, True) for ``T | None`` / ``Optional[T]``; (tp, False) otherwise."""
    if get_origin(tp) in (Union, UnionType):
        args = get_args(tp)
        rest = [arg for arg in args if arg is not NoneType]
        if len(rest) == 1 and len(rest) < len(args):
            return rest[0], True
    return tp, False


def _file_shape(tp: Any) -> tuple[Optional[str], bool]:
    """
    ("one" | "many" | "model" | "all" | None, optional) for a Files[...]
    type: UploadedFile, list[UploadedFile], a Pydantic model, or
    dict[str, list[UploadedFile]].
    """
    inner, optional = _strip_optional(tp)
    if inner is UploadedFile:
        return "one", optional
    if _is_model(inner):
        return ("model", False) if not optional else (None, True)
    origin, args = get_origin(inner), get_args(inner)
    if origin is list and args == (UploadedFile,):
        return "many", optional
    if (
        origin is dict
        and not optional
        and len(args) == 2
        and args[0] is str
        and _file_shape(args[1]) == ("many", False)
    ):
        return "all", False
    return None, optional


def mentions_uploaded_file(tp: Any) -> bool:
    """True if a type is, or contains, UploadedFile (``list[UploadedFile]``, ...)."""
    if tp is UploadedFile:
        return True
    return any(mentions_uploaded_file(arg) for arg in get_args(tp))


def _parameter_hints(func: Callable[..., Any], qualname: str) -> dict[str, Any]:
    """
    The handler's resolved annotations. If some cannot be resolved (a name
    imported only for type checking, say), the others are resolved one by
    one; an unresolvable marked annotation is an error, since the
    parameter could not be injected.
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
            if any(
                marker in annotation
                for marker in (
                    "RequestBody",
                    "QueryParams",
                    "Files",
                    "Headers",
                    "Cookies",
                )
            ):
                raise TypeError(
                    f"{qualname}: cannot resolve the annotation {annotation!r} "
                    f"of parameter {name!r}: {exc}"
                ) from exc
            hints[name] = annotation
    return hints


def handler_params(func: Callable[..., Any]) -> HandlerParams:
    """
    Returns (and caches) the parameter plan of a handler. The first two
    parameters (``self`` and ``req``) are skipped.

    Raises TypeError for a marker around an unsupported type, or when a
    handler declares more than one RequestBody.
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


def _body_param(qualname: str, param: inspect.Parameter, inner: Any) -> SourcedParam:
    source = BodySource()
    if _is_model(inner):
        return SourcedParam(param.name, inner, source)
    try:
        adapter: TypeAdapter[Any] = TypeAdapter(inner)
    # pylint: disable-next=W0718
    except Exception as exc:  # PydanticSchemaGenerationError, TypeError, ...
        raise TypeError(
            f"{qualname}: parameter {param.name!r} is a RequestBody of type "
            f"{inner!r}, which Pydantic cannot validate: {exc}"
        ) from exc
    return SourcedParam(param.name, inner, source, adapter)


def _build_plan(func: Callable[..., Any]) -> HandlerParams:
    # Parameters: [0]=self, [1]=req, others start at index 2
    parameters = list(inspect.signature(func).parameters.values())[2:]
    qualname = getattr(func, "__qualname__", repr(func))
    hints = _parameter_hints(func, qualname)

    body: Optional[SourcedParam] = None
    query: list[SourcedParam] = []
    headers: list[SourcedParam] = []
    cookies: list[SourcedParam] = []
    files: list[SourcedParam] = []
    file_models: list[SourcedParam] = []
    file_fields: dict[str, Any] = {}
    all_files: Optional[str] = None
    unmarked: list[tuple[str, Type[BaseModel]]] = []

    for param in parameters:
        annotation = hints.get(param.name, param.annotation)
        inner, source = _split_annotation(annotation)
        if source is None:
            if _is_model(inner):
                unmarked.append((param.name, inner))
            continue

        if isinstance(source, BodySource):
            if body is not None:
                raise TypeError(
                    f"{qualname}: parameters {body.name!r} and {param.name!r} are "
                    "both RequestBody. A request has one body; use one model."
                )
            body = _body_param(qualname, param, inner)

        elif isinstance(source, QuerySource):
            if not _is_model(inner):
                raise TypeError(
                    f"{qualname}: parameter {param.name!r} is marked as "
                    f"QuerySource but {inner!r} is not a Pydantic model."
                )
            query.append(SourcedParam(param.name, inner, source))

        elif isinstance(source, (HeaderSource, CookieSource)):
            marker = "Headers" if isinstance(source, HeaderSource) else "Cookies"
            if not _is_model(inner):
                raise TypeError(
                    f"{qualname}: parameter {param.name!r} is {marker}[{inner!r}], "
                    "but it needs a Pydantic model whose fields name the "
                    f"{source.location}s."
                )
            sourced = SourcedParam(
                param.name,
                inner,
                source,
                names=_http_names(qualname, param.name, inner, source),
            )
            (headers if isinstance(source, HeaderSource) else cookies).append(sourced)

        elif isinstance(source, FileSource):
            shape, optional = _file_shape(inner)
            if shape is None:
                raise TypeError(
                    f"{qualname}: parameter {param.name!r} is Files[{inner!r}]. "
                    "Use Files[UploadedFile], Files[list[UploadedFile]] (either "
                    "optionally | None), Files[Model] or "
                    "Files[dict[str, list[UploadedFile]]]."
                )
            if shape == "model":
                for field_name, info in inner.model_fields.items():
                    if not mentions_uploaded_file(info.annotation):
                        raise TypeError(
                            f"{qualname}: parameter {param.name!r} is "
                            f"Files[{inner.__name__}], but "
                            f"{inner.__name__}.{field_name} is not a file field. "
                            "Form fields belong in the RequestBody model."
                        )
                file_models.append(SourcedParam(param.name, inner, source))
                continue
            if shape == "all":
                if all_files is not None:
                    raise TypeError(
                        f"{qualname}: parameters {all_files!r} and {param.name!r} "
                        "both take every file of the request."
                    )
                all_files = param.name
                continue
            if param.default is not inspect.Parameter.empty:
                default = param.default
            elif optional:
                default = None
            elif shape == "many":
                # No file sent under that name is an empty list.
                default = Field(default_factory=list)
            else:
                default = ...
            file_fields[param.name] = (inner, default)
            files.append(SourcedParam(param.name, inner, source))

    _check_file_field_overlap(qualname, files, file_models)

    files_model: Optional[Type[BaseModel]] = None
    if file_fields:
        try:
            files_model = create_model(  # type: ignore[call-overload]
                f"{getattr(func, '__name__', 'handler')}_files", **file_fields
            )
        # pylint: disable-next=W0718
        except Exception as exc:
            raise TypeError(
                f"{qualname}: cannot use the Files parameters "
                f"{sorted(file_fields)}: {exc}"
            ) from exc

    return HandlerParams(
        body=body,
        query=tuple(query),
        headers=tuple(headers),
        cookies=tuple(cookies),
        files=tuple(files),
        files_model=files_model,
        file_models=tuple(file_models),
        all_files=all_files,
        unmarked=tuple(unmarked),
    )


def _http_names(
    qualname: str, param_name: str, model: Type[BaseModel], source: ParamSource
) -> tuple[tuple[str, str, bool], ...]:
    """
    (model input key, HTTP name, list field) for each field of a Headers or
    Cookies model. The input key is the field's alias, or its name. A header
    without an alias is the field name with hyphens, lower-cased (headers
    ignore case); a cookie is the alias or name as written.
    """
    names: list[tuple[str, str, bool]] = []
    seen: dict[str, str] = {}
    is_header = isinstance(source, HeaderSource)
    for field_name, info in model.model_fields.items():
        alias = (
            info.validation_alias if info.validation_alias is not None else (info.alias)
        )
        if alias is not None and not isinstance(alias, str):
            raise TypeError(
                f"{qualname}: {model.__name__}.{field_name} of parameter "
                f"{param_name!r} needs a plain string alias to name its "
                f"{source.location}."
            )
        key = alias if isinstance(alias, str) else field_name
        if is_header:
            http_name = (alias or field_name.replace("_", "-")).lower()
        else:
            http_name = key
        if http_name in seen:
            raise TypeError(
                f"{qualname}: {model.__name__}.{seen[http_name]} and "
                f"{model.__name__}.{field_name} both read the {source.location} "
                f"{http_name!r}."
            )
        seen[http_name] = field_name
        names.append((key, http_name, _is_collection(info.annotation)))
    return tuple(names)


def _is_collection(annotation: Any) -> bool:
    """list[str], set[str], Optional[list[str]], ... (not str or bytes)."""
    inner, _ = _strip_optional(annotation)
    return get_origin(inner) in (list, set, tuple, frozenset)


def _field_keys(name: str, info: Any) -> set[str]:
    """A model field's name and string aliases: the keys a form may use."""
    keys = {name}
    for alias in (info.alias, info.validation_alias):
        if isinstance(alias, str):
            keys.add(alias)
    return keys


def _model_keys(model: Type[BaseModel]) -> set[str]:
    keys: set[str] = set()
    for name, info in model.model_fields.items():
        keys |= _field_keys(name, info)
    return keys


def _check_file_field_overlap(
    qualname: str,
    files: list[SourcedParam],
    file_models: list[SourcedParam],
) -> None:
    """Each file field may be bound by one Files parameter only."""
    owners: dict[str, str] = {}
    claims = [(p.name, {p.name}) for p in files] + [
        (p.name, _model_keys(p.model)) for p in file_models
    ]
    for owner, keys in claims:
        for key in sorted(keys):
            if key in owners and owners[key] != owner:
                raise TypeError(
                    f"{qualname}: the file field {key!r} is taken by both the "
                    f"Files parameters {owners[key]!r} and {owner!r}."
                )
            owners[key] = owner


def check_request_hook_params(func: Callable[..., Any], what: str) -> HandlerParams:
    """
    Validates the parameters of a middleware method or a @before_request
    hook. After ``req`` they may only declare Headers[...], Cookies[...] and
    QueryParams[...]: these run for many endpoints, before an endpoint's
    @consumes check, so there is no body or file for them, and nothing
    would fill any other parameter.
    """
    plan = handler_params(func)
    if plan.body is not None or plan.reads_files:
        raise TypeError(
            f"{what}: RequestBody and Files parameters are only available on "
            "endpoints, which declare the body's media type with @consumes."
        )
    allowed = {p.name for p in (*plan.query, *plan.headers, *plan.cookies)}
    parameters = list(inspect.signature(_underlying(func)).parameters.values())[2:]
    for param in parameters:
        if param.name not in allowed:
            raise TypeError(
                f"{what}: nothing fills the parameter {param.name!r}. After req, "
                "only Headers[...], Cookies[...] and QueryParams[...] parameters "
                "are injected; keep other values in a local variable or a "
                "class attribute."
            )
    return plan


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
    body = plan.body

    if plan.unmarked:
        name, model = plan.unmarked[0]
        raise TypeError(
            f"{qualname}: parameter {name!r} is a Pydantic model without a "
            f"source. Annotate it as RequestBody[{model.__name__}] or "
            f"QueryParams[{model.__name__}]."
        )
    if http_method == "GET" and consumes:
        raise UnexpectedDecorator("GET endpoints can't consume request bodies.")
    if body is not None and not consumes:
        raise TypeError(
            f"{qualname}: parameter {body.name!r} is a RequestBody, but the "
            "endpoint has no @consumes(...) saying how to read the body."
        )
    if body is not None and not body.is_model and consumes in _FORM_MEDIA_TYPES:
        raise TypeError(
            f"{qualname}: parameter {body.name!r} is RequestBody[{body.model!r}], "
            "but a form body is one set of fields. Use a Pydantic model; "
            "types such as list[Model] are supported for JSON bodies."
        )
    if plan.reads_files and consumes != MediaType.MULTIPART_FORM_DATA:
        raise TypeError(
            f"{qualname}: Files parameters {plan.file_param_names} need "
            "@consumes(MediaType.MULTIPART_FORM_DATA)."
        )
    if plan.reads_files and body is not None and body.is_model:
        file_names = {p.name for p in plan.files}
        for file_model in plan.file_models:
            file_names |= _model_keys(file_model.model)
        for name, info in body.model.model_fields.items():
            if mentions_uploaded_file(info.annotation):
                raise TypeError(
                    f"{qualname}: {body.model.__name__}.{name} is a file field, "
                    "but with Files parameters the RequestBody receives the "
                    "form fields only. Move the file to a Files parameter, or "
                    "drop the Files parameters to keep files in the model."
                )
            clash = _field_keys(name, info) & file_names
            if clash:
                raise TypeError(
                    f"{qualname}: field {sorted(clash)[0]!r} is both a "
                    f"{body.model.__name__} field and a file field of a Files "
                    "parameter."
                )
    return plan
