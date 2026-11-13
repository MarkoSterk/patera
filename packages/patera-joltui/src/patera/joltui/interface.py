"""Dispatch JoltUI's fetchHTML protocol through ordinary Patera requests.

The application owns the HTTP endpoint: the ``@dispatcher`` POST route of a
``JoltuiController`` calls ``self.<interface>.dispatch(req)`` on the
controller's single injected ``PateraJoltui``; the controller's other endpoints
are ordinary. The interface is an injectable service that receives its
component groups through ``ComponentGroup[...]`` annotations. A small dispatch
middleware (order -102) selects the component before CORS, database sessions,
and authentication run, so decorators on component methods and group handlers
keep working.
"""

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
    overload,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from patera import (
    HttpStatus,
    BaseExtension,
    MediaType,
    Request,
    Response,
    run_sync_or_async,
)
from patera.controller.params import BodySource, _split_annotation
from patera.controller.utilities import _build_model
from patera.controller import Controller, post
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

#: Request scope keys set while a component request is resolved.
_PAYLOAD_KEY = "patera.joltui"
_INTERFACE_KEY = "patera.joltui.interface"

#: Marks the endpoint that receives the fetchHTML envelope (see dispatcher);
#: the value is the path @dispatcher registered.
_DISPATCHER_ATTRIBUTE = "__joltui_dispatcher__"

#: Decorators neither the dispatcher endpoint nor its JoltuiController may
#: carry: it would be ambiguous whether they guard the envelope or the
#: component, and the middleware that reads them sees the selected component.
_IGNORED_ATTRIBUTES: dict[str, str] = {
    "_authentication": "@login_required/@role_required",
    "_transactional": "@transactional",
    "_cors_options": "@cors",
    "_disable_cors": "@no_cors",
}


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
            if body_parameter is not None and body_parameter[0] not in kwargs:
                # Without @consumes the component body is the JSON payload.
                name, model = body_parameter
                kwargs[name] = _build_model(
                    model, await request.json(), location="body"
                )
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
        raise TypeError(
            "Component handlers require (self, req[, body: RequestBody[Model]])"
        )
    parameter = parameters[1]
    model, source = _split_annotation(
        get_type_hints(method, include_extras=True).get(parameter.name)
    )
    if (
        not isinstance(source, BodySource)
        or not isinstance(model, type)
        or not issubclass(model, BaseModel)
    ):
        raise TypeError(
            "The third component handler argument must be RequestBody[Model] "
            "with a Pydantic model"
        )
    return parameter.name, model


class _JoltuiDispatchMiddleware(MiddlewareBase):
    # Resolve before CORS (-101), database sessions (-100), and auth (-99).
    _order_: ClassVar[int] = -102
    _middleware: ClassVar[bool] = True

    def __init__(self, app: Any, next_app: Any) -> None:
        super().__init__(app, next_app)
        # The chain is built after every controller is registered, so the
        # JoltUI controllers can be checked once, before the first request.
        self._interfaces = _check_controllers(app)

    async def middleware(self, req: Request) -> Response:
        # OPTIONS preflights reach the endpoint too, without an envelope.
        marker = getattr(req.endpoint, _DISPATCHER_ATTRIBUTE, None)
        if req.method == "POST" and marker is not None:
            controller = req.endpoint.__self__  # type: ignore[attr-defined]
            await self._interfaces[id(controller)].resolve(req)
        return await self.next(req)


def _interface_attribute(controller: "JoltuiController") -> str:
    """The name of the controller's single injected PateraJoltui attribute."""
    names = [
        name
        for name, definition in type(controller).__autowires__.items()
        if isinstance(definition.target_type, type)
        and issubclass(definition.target_type, PateraJoltui)
    ]
    if len(names) != 1:
        found = ", ".join(sorted(names)) if names else "none"
        raise TypeError(
            f"{type(controller).__name__}: a JoltuiController must inject exactly "
            f"one PateraJoltui interface (found: {found}). Its @dispatcher "
            "endpoint dispatches to that interface."
        )
    return names[0]


def _check_controllers(app: Any) -> dict[int, "PateraJoltui"]:
    """Validate JoltuiControllers and @dispatcher endpoints.

    Returns the interface of each controller that has a dispatcher endpoint.
    """
    interfaces: dict[int, PateraJoltui] = {}
    controllers: dict[int, JoltuiController] = {}
    for controller in list(app._controllers.values()):
        if not isinstance(controller, JoltuiController):
            continue
        name = type(controller).__name__
        for attribute, label in _IGNORED_ATTRIBUTES.items():
            if getattr(controller, attribute, None):
                raise TypeError(_misplaced(name, label, "a JoltuiController"))
        interfaces[id(controller)] = getattr(
            controller, _interface_attribute(controller)
        )
        controllers[id(controller)] = controller

    dispatchers: dict[int, str] = {}
    for (url_path, method), (endpoint, name) in app.router._rules.items():
        if getattr(endpoint, _DISPATCHER_ATTRIBUTE, None) is None:
            continue
        where = f"{name} ({method} {url_path})"
        controller = getattr(endpoint, "__self__", None)
        if id(controller) not in interfaces:
            raise TypeError(
                f"{where}: @dispatcher endpoints belong to a JoltuiController "
                f"subclass, not {type(controller).__name__}."
            )
        route = getattr(endpoint, "_handler", None) or {}
        if method != "POST" or route.get("path") != getattr(
            endpoint, _DISPATCHER_ATTRIBUTE
        ):
            raise TypeError(
                f"{where}: @dispatcher registers its own POST route; remove the "
                "other route decorator (@post, @get, ...) from this endpoint."
            )
        previous = dispatchers.setdefault(id(controller), endpoint.__name__)
        if previous != endpoint.__name__:
            raise TypeError(
                f"{type(controller).__name__}: a JoltuiController has a single "
                f"@dispatcher endpoint (found {previous} and {endpoint.__name__})."
            )
        for attribute, label in _IGNORED_ATTRIBUTES.items():
            if getattr(endpoint, attribute, None):
                raise TypeError(_misplaced(where, label, "the @dispatcher endpoint"))

    for key, controller in controllers.items():
        if key not in dispatchers:
            app.logger.warning(
                f"{type(controller).__name__} has no @dispatcher endpoint; "
                "it serves no JoltUI components."
            )
    served = {id(interfaces[key]) for key in dispatchers}
    for extension in list(app._extensions.values()):
        if isinstance(extension, PateraJoltui) and id(extension) not in served:
            app.logger.warning(
                f"{type(extension).__name__} has no @dispatcher endpoint; its "
                "components cannot be requested."
            )
    return {key: interfaces[key] for key in dispatchers}


def _misplaced(where: str, label: str, owner: str) -> str:
    return (
        f"{where}: {label} on {owner} is not supported, because it is "
        "ambiguous whether it guards the component request or the component, "
        "and the middleware sees the selected component. Put it on the group "
        "handler or the component method instead."
    )


class JoltuiConfig(BaseModel):
    """Configuration of a JoltUI interface (currently no options)."""

    @model_validator(mode="before")
    @classmethod
    def reject_components_path(cls, data: Any) -> Any:
        if isinstance(data, dict) and "COMPONENTS_PATH" in data:
            raise ValueError(
                "COMPONENTS_PATH was removed: the application now defines the "
                "component endpoint itself. Add a @dispatcher POST endpoint to "
                "a JoltuiController that injects YourInterface and returns "
                "await self.<interface>.dispatch(req)."
            )
        return data


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
    value = req.scope.get(_PAYLOAD_KEY)
    if not isinstance(value, JoltuiRequest):
        raise RuntimeError("This request is not a JoltUI component request")
    return value


class PateraJoltui(BaseExtension[Any, JoltuiConfig]):
    """
    Injectable service that renders declaratively registered component groups.

    Subclass it, declare groups with ``ComponentGroup[Handler]`` annotations,
    inject the subclass into a :class:`JoltuiController` and call
    :meth:`dispatch` from the controller's ``@dispatcher`` endpoint.
    """

    def init(self) -> None:
        self.configs  # validate configuration early (COMPONENTS_PATH removed)
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

        _register_dispatch_middleware(self.app)

    def _excluded(self, target: Any) -> bool:
        return bool(
            getattr(target, "_ignore", False)
            or (
                getattr(target, "_development", False)
                and not self.app.get_conf("DEBUG", False)
            )
        )

    async def resolve(self, req: Request) -> None:
        """
        Select the component for this request before ordinary middleware
        inspects ``req.route_handler``. Called by the dispatch middleware.
        """
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
        req.scope[_PAYLOAD_KEY] = payload
        req.scope[_INTERFACE_KEY] = self
        req._route_handler = handler
        get_request_context().controller = handler.__self__
        limit = getattr(handler, "_max_content_length", req.max_content_length)
        req.max_content_length = limit
        if limit is not None and len(await req.body()) > limit:
            raise RequestBodyTooLarge(limit)

    async def dispatch(self, req: Request) -> Response:
        """
        Render the component selected for this request.

        Call it from the ``@dispatcher`` endpoint of the
        :class:`JoltuiController` that injects this interface and return its
        response. The dispatch middleware has already selected
        the component, applied its authentication, CORS, transaction, and
        body-size rules, and validated the JoltUI envelope.
        """
        if req.scope.get(_INTERFACE_KEY) is not self:
            raise RuntimeError(
                f"{type(self).__name__}.dispatch() must be called from the "
                "@dispatcher endpoint of a JoltuiController that injects "
                f"{type(self).__name__}"
            )
        handler = req.route_handler
        assert isinstance(handler, MethodType)
        controller = handler.__self__
        assert isinstance(controller, JoltuiGroupHandler)
        return await controller(handler, req)


def _register_dispatch_middleware(app: Any) -> None:
    if _JoltuiDispatchMiddleware not in app._middleware_classes.values():
        app.register_middleware(_JoltuiDispatchMiddleware)


@overload
def dispatcher(func: F, /) -> F: ...


@overload
def dispatcher(
    url_path: str = "",
    /,
    *,
    open_api_spec: bool = False,
    tags: list[str] | None = None,
) -> Callable[[F], F]: ...


def dispatcher(
    target: Any = "",
    /,
    *,
    open_api_spec: bool = False,
    tags: list[str] | None = None,
) -> Any:
    """
    Register the POST route of a :class:`JoltuiController` that receives
    JoltUI's fetchHTML envelope and returns
    ``await self.<interface>.dispatch(req)``.

    ``@dispatcher`` serves the controller's own path; ``@dispatcher("/sub")``
    serves a path below it. It replaces ``@post``, so do not add another route
    decorator. The route is left out of the OpenAPI document unless
    ``open_api_spec=True``. A controller has at most one dispatcher. Put
    authentication, transaction, and CORS decorators on group handlers or
    component methods, not on this endpoint or its controller.
    """
    if callable(target):
        return dispatcher()(target)
    if not isinstance(target, str):
        raise TypeError("@dispatcher takes an optional URL path string")
    url_path = target

    def decorate(func: F) -> F:
        if (getattr(func, "_handler", None) or {}).get("http_handler"):
            raise TypeError(
                f"{func.__name__}: @dispatcher registers its own POST route; "
                "remove the other route decorator (@post, @get, ...)."
            )
        endpoint = post(url_path, open_api_spec=open_api_spec, tags=tags)(func)
        setattr(endpoint, _DISPATCHER_ATTRIBUTE, url_path)
        return endpoint  # type: ignore[return-value]

    return decorate


class JoltuiController(Controller):
    """
    Controller that serves JoltUI's fetchHTML component requests.

    Its single ``@dispatcher`` POST endpoint receives the envelope and returns
    ``await self.<interface>.dispatch(req)``, where ``<interface>`` is the
    controller's single injected :class:`PateraJoltui`. Every other endpoint
    is an ordinary endpoint with ordinary decorators.

    Do not put ``@login_required``, ``@role_required``, ``@transactional``,
    ``@cors``, or ``@no_cors`` on this controller or on its dispatcher
    endpoint; put them on group handlers or component methods. Endpoints other
    than the dispatcher take them as usual.
    """

    def __init__(self, app: Any, *args: Any, **kwargs: Any) -> None:
        super().__init__(app, *args, **kwargs)
        # The middleware checks the controller (one interface, one dispatcher,
        # no ambiguous decorators) when the application is built.
        _register_dispatch_middleware(app)
