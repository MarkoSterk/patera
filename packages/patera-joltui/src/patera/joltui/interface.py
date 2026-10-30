"""Dispatch JoltUI's fetchHTML protocol through ordinary Patera requests."""

from __future__ import annotations

import re
import inspect
from functools import wraps
from types import MethodType
from typing import (
    ClassVar,
    Annotated,
    Any,
    Callable,
    TypeAlias,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from patera import (
    HttpStatus,
    BaseExtension,
    MediaType,
    Request,
    Response,
    run_sync_or_async,
)
from patera.controller.utilities import _build_model, _unwrap_annotated
from patera.controller import Controller, path, post
from patera.exceptions.http_exceptions import (
    BaseHttpException,
    InvalidRequestBody,
    RequestBodyTooLarge,
)
from patera.ctx import get_request_context
from patera.middleware import MiddlewareBase
from patera.injectable import _own_annotations, _resolve_annotation

T = TypeVar("T", bound="JoltuiGroupHandler")
F = TypeVar("F", bound=Callable[..., Any])


class _ComponentGroup:
    pass


ComponentGroup: TypeAlias = Annotated[T, _ComponentGroup()]


def _name(value: str, *, tag: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Component and group names must be non-empty strings")
    return value.strip().lower() if tag else value.strip()


def group(name: str) -> Callable[[type[T]], type[T]]:
    """Name a group; only groups declared on an interface are exposed."""
    name = _name(name)

    def decorate(cls: type[T]) -> type[T]:
        if not issubclass(cls, JoltuiGroupHandler):
            raise TypeError("@group requires a JoltuiGroupHandler subclass")
        cls.__joltui_group__ = name
        return cls

    return decorate


def component(tag: str) -> Callable[[F], F]:
    """Expose a handler under a case-insensitive component tag."""
    tag = _name(tag, tag=True)

    def decorate(func: F) -> F:
        setattr(func, "__joltui_component__", tag)
        return func

    return decorate


class JoltuiGroupHandler(Controller):
    """App-scoped controller with normal injection and lifecycle decorators."""

    __joltui_group__: ClassVar[str]

    async def __call__(self, method: Callable, req: Request) -> Response:
        @wraps(method)
        async def render(request: Request, **kwargs: Any) -> Response:
            body_parameter = _body_parameter(method)
            if body_parameter is not None:
                name, model = body_parameter
                kwargs[name] = _build_model(model, await request.json())
            result = await run_sync_or_async(method, request, **kwargs)
            _require_html_response(result)
            return result

        result = await super().__call__(render, req)
        _require_html_response(result)
        return result


def _require_html_response(result: Any) -> None:
    if not isinstance(result, Response):
        raise TypeError("JoltUI component handlers must return an HTML Response")
    # Normal endpoint decorators and lifecycle hooks may return structured
    # client/server errors. Preserve those responses and their status codes.
    if int(result.status_code) >= 400:
        return
    content_type = result.content_type or result.media_type or ""
    if content_type.split(";", 1)[0].strip().lower() != MediaType.TEXT_HTML.value:
        raise TypeError("JoltUI component responses must use text/html")


def _body_parameter(method: Callable) -> tuple[str, type[BaseModel]] | None:
    # Bound method parameters are (req, body); wraps preserves the original
    # signature and annotations through ordinary endpoint decorators.
    parameters = list(inspect.signature(method).parameters.values())
    if len(parameters) == 1:
        return None
    if len(parameters) != 2 or parameters[1].kind not in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    ):
        raise TypeError("Component handlers require (self, req[, body: BaseModel])")
    parameter = parameters[1]
    model = _unwrap_annotated(
        get_type_hints(method, include_extras=True).get(parameter.name)
    )
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError("The third component handler argument must be a Pydantic model")
    return parameter.name, model


class _JoltuiDispatchMiddleware(MiddlewareBase):
    # Resolve before CORS (-101), database sessions (-100), and auth (-99).
    _order_: ClassVar[int] = -102
    _middleware: ClassVar[bool] = True

    async def middleware(self, req: Request) -> Response:
        extension = getattr(req.route_handler, "__joltui_interface__", None)
        if extension is not None and req.method == "POST":
            await extension.resolve(req)
        return await self.next(req)


class JoltuiConfig(BaseModel):
    COMPONENTS_PATH: str = "/joltui/components"

    @field_validator("COMPONENTS_PATH")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/") or any(c in value for c in "?#{<"):
            raise ValueError("COMPONENTS_PATH must be an absolute, literal URL path")
        return value


class JoltuiRequest(BaseModel):
    """Frontend metadata, separate from the HTTP request's URL parameters."""

    model_config = ConfigDict(strict=True, populate_by_name=True)
    tag_name: str | None = Field(default=None, alias="tagName", min_length=1)
    group_name: str = Field(default="default", alias="groupName")
    route_parameters: dict[str, str | int | float] = Field(
        default_factory=dict, alias="routeParameters"
    )
    query_parameters: dict[str, str] = Field(
        default_factory=dict, alias="queryParameters"
    )
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tag_name")
    @classmethod
    def normalize_tag(cls, value: str | None) -> str | None:
        return _name(value, tag=True) if value is not None else None

    @field_validator("group_name", mode="before")
    @classmethod
    def normalize_group(cls, value: Any) -> Any:
        return (
            (value.strip() or "default")
            if isinstance(value, str)
            else ("default" if value is None else value)
        )

    @field_validator(
        "route_parameters", "query_parameters", "attributes", mode="before"
    )
    @classmethod
    def normalize_mapping(cls, value: Any) -> Any:
        return {} if value is None else value


def joltui_request(req: Request) -> JoltuiRequest:
    """Return metadata during a component dispatch, without replacing Request."""
    value = req.scope.get("patera.joltui")
    if not isinstance(value, JoltuiRequest):
        raise RuntimeError("This request is not a JoltUI component request")
    return value


class PateraJoltui(BaseExtension[Any, JoltuiConfig]):
    """Mount a POST endpoint for declaratively registered component groups."""

    def init(self) -> None:
        declarations: dict[str, type[JoltuiGroupHandler]] = {}
        for cls in reversed(type(self).__mro__):
            for name, raw in _own_annotations(cls).items():
                declarations.pop(name, None)
                if isinstance(raw, str):
                    if not re.search(r"\b(?:ComponentGroup|Annotated)\s*\[", raw):
                        continue
                    raw = _resolve_annotation(cls, name, raw)
                if get_origin(raw) is not Annotated:
                    continue
                target, *metadata = get_args(raw)
                if not any(isinstance(m, _ComponentGroup) for m in metadata):
                    continue
                if not isinstance(target, type) or not issubclass(
                    target, JoltuiGroupHandler
                ):
                    raise TypeError(
                        f"{name}: ComponentGroup requires a JoltuiGroupHandler"
                    )
                declarations[name] = target

        self._handlers: dict[tuple[str, str], MethodType] = {}
        groups: set[str] = set()
        for name, target in declarations.items():
            group_name = getattr(target, "__joltui_group__", None)
            if group_name is None:
                raise TypeError(f"{target.__name__} needs a @group decorator")
            if group_name in groups:
                raise ValueError(f"Duplicate JoltUI group: {group_name}")
            groups.add(group_name)
            if self._excluded(target):
                continue
            handler = self._resolve_dependency(target)
            setattr(self, name, handler)
            members: dict[str, Any] = {}
            for base in reversed(target.__mro__):
                members.update(vars(base))
            for method_name, method in members.items():
                tag = getattr(method, "__joltui_component__", None)
                if tag is None:
                    continue
                if self._excluded(method):
                    continue
                key = (group_name, tag)
                if key in self._handlers:
                    raise ValueError(f"Duplicate JoltUI component: {group_name}/{tag}")
                self._handlers[key] = getattr(handler, method_name)
                _body_parameter(self._handlers[key])

        extension = self

        @path(self.configs.COMPONENTS_PATH, open_api_spec=False)
        class JoltuiComponents(Controller):
            @post("")
            async def render_component(self, req: Request) -> Response:
                return await extension.dispatch(req)

        JoltuiComponents.__name__ = f"{type(self).__name__}Components"
        setattr(JoltuiComponents.render_component, "__joltui_interface__", self)
        self.app.register_controller(JoltuiComponents)
        if _JoltuiDispatchMiddleware not in self.app._middleware_classes.values():
            self.app.register_middleware(_JoltuiDispatchMiddleware)

    def _excluded(self, target: Any) -> bool:
        return bool(
            getattr(target, "_ignore", False)
            or (
                getattr(target, "_development", False)
                and not self.app.get_conf("DEBUG", False)
            )
        )

    async def resolve(self, req: Request) -> None:
        """Select the effective endpoint before ordinary middleware inspects it."""
        try:
            payload = JoltuiRequest.model_validate(await req.json())
        except ValidationError as exc:
            raise InvalidRequestBody("Invalid JoltUI component request") from exc
        if payload.tag_name is None:
            raise InvalidRequestBody("tagName is required for component dispatch")
        handler = self._handlers.get((payload.group_name, payload.tag_name))
        if handler is None:
            raise BaseHttpException(
                "Unknown JoltUI component", status_code=HttpStatus.NOT_FOUND
            )
        req.scope["patera.joltui"] = payload
        req._route_handler = handler
        get_request_context().controller = handler.__self__
        # The shared endpoint's body limit protects envelope parsing. A smaller
        # component limit is checked once the envelope identifies the handler.
        limit = getattr(handler, "_max_content_length", req.max_content_length)
        req.max_content_length = limit
        if limit is not None and len(await req.body()) > limit:
            raise RequestBodyTooLarge(limit)

    async def dispatch(self, req: Request) -> Response:
        """Fallback for direct invocation of the registered controller."""
        await self.resolve(req)
        handler = req.route_handler
        assert isinstance(handler, MethodType)
        controller = handler.__self__
        assert isinstance(controller, JoltuiGroupHandler)
        return await controller(handler, req)
