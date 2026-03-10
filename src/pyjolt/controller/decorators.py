"""
Controller decorators
"""

from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    ParamSpec,
    Protocol,
    Type,
    cast,
)
from functools import wraps
import inspect

from .controller import Controller, Descriptor
from .utilities import (
    _extract_response_type,
    get_type_hints,
    _unwrap_annotated,
    _is_pydantic_model,
    _content_type_matches,
    _read_payload_for_consumes,
    _build_model,
)
from ..response import Response
from ..request import Request
from ..utilities import run_sync_or_async
from ..exceptions import MethodNotControllerMethod, UnexpectedDecorator
from ..media_types import MediaType
from ..http_methods import HttpMethod
from ..http_statuses import HttpStatus

P = ParamSpec("P")
R = Any  # Return type of the *original* endpoint method

# Any bound method (sync or async) -> async method returning Response
AsyncMethod = Callable[..., Awaitable["Response"]]


# pylint: disable-next=R0903
class _EndpointDecorator(Protocol):
    """A decorator that accepts a sync or async method and returns an async method."""

    def __call__(self, func: Callable[..., Any]) -> AsyncMethod: ...


# pylint: disable-next=R0903
class EndpointDecoratorFn(Protocol):
    """Callable returned by HTTP method factories (post/put/patch/delete)."""

    def __call__(
        self,
        url_path: str,
        open_api_spec: bool = True,
        tags: Optional[list[str]] = None,
    ) -> _EndpointDecorator: ...


def get(
    url_path: str, open_api_spec: bool = True, tags: Optional[list[str]] = None
) -> _EndpointDecorator:
    """GET http handler decorator."""

    def decorator(func: Callable[..., Any]) -> AsyncMethod:
        @wraps(func)
        async def wrapper(self: Controller, *args: Any, **kwargs: Any) -> "Response":
            if not isinstance(self, Controller):
                raise MethodNotControllerMethod(
                    f"Method {func.__name__} is not part of a valid controller class"
                )

            # pre-hooks
            req: "Request" = args[0]  # type: ignore[index]
            for m in reversed(getattr(self, "_controller_decorator_methods", []) or []):
                await run_sync_or_async(m, req)
            for m in getattr(self, "_before_request_methods", []) or []:
                await run_sync_or_async(m, req)

            # call the original (sync or async)
            response: "Response" = await run_sync_or_async(func, self, *args, **kwargs)

            # post-hooks
            for m in getattr(self, "_after_request_methods", []) or []:
                await run_sync_or_async(m, response)
            return response

        merged = {
            **(getattr(func, "_handler", {}) or {}),
            "http_method": HttpMethod.GET.value,
            "path": url_path,
            "open_api_spec": open_api_spec,
            "tags": tags if tags is not None else [],
        }
        if merged.get("consumes", False):
            raise UnexpectedDecorator("GET endpoints can't consume request bodies.")
        # pylint: disable=protected-access
        wrapper._handler = merged  # type: ignore[attr-defined]
        return wrapper

    return cast(_EndpointDecorator, decorator)


def endpoint_decorator_factory(http_method: HttpMethod) -> EndpointDecoratorFn:
    def endpoint_decorator(
        url_path: str,
        open_api_spec: bool = True,
        tags: Optional[list[str]] = None,
    ) -> _EndpointDecorator:
        def decorator(func: Callable[..., Any]) -> AsyncMethod:
            @wraps(func)
            async def wrapper(
                self: Controller, *args: Any, **kwargs: Any
            ) -> "Response":
                if not isinstance(self, Controller):
                    raise MethodNotControllerMethod(
                        f"Method {func.__name__} is not part of a valid controller class"
                    )

                # Optionally infer/record expected response type for endpoint
                req: "Request" = args[0]  # type: ignore[index]
                if req.response.expected_body_type is None:
                    expected = _extract_response_type(func)
                    # pylint: disable=protected-access
                    req.response._set_expected_body_type(expected)

                # pre-hooks
                for m in reversed(
                    getattr(self, "_controller_decorator_methods", []) or []
                ):
                    await run_sync_or_async(m, req)
                for m in getattr(self, "_before_request_methods", []) or []:
                    await run_sync_or_async(m, req)

                # call the original (sync or async)
                response: "Response" = await run_sync_or_async(
                    func, self, *args, **kwargs
                )

                # post-hooks
                for m in getattr(self, "_after_request_methods", []) or []:
                    await run_sync_or_async(m, response)
                return response

            # attach metadata
            # pylint: disable=protected-access
            wrapper._handler = {  # type: ignore[attr-defined]
                **(getattr(func, "_handler", {}) or {}),
                "http_method": http_method.value,
                "path": url_path,
                "open_api_spec": open_api_spec,
                "tags": tags if tags is not None else [],
            }
            return wrapper

        return cast(_EndpointDecorator, decorator)

    return endpoint_decorator


post = endpoint_decorator_factory(HttpMethod.POST)
put = endpoint_decorator_factory(HttpMethod.PUT)
patch = endpoint_decorator_factory(HttpMethod.PATCH)
delete = endpoint_decorator_factory(HttpMethod.DELETE)


def socket(url_path: str) -> _EndpointDecorator:
    """SOCKET http handler decorator."""

    def decorator(func: Callable[..., Any]) -> AsyncMethod:
        @wraps(func)
        async def wrapper(self: Controller, *args: Any, **kwargs: Any):
            if not isinstance(self, Controller):
                raise MethodNotControllerMethod(
                    f"Method {func.__name__} is not part of a valid controller class"
                )
            await run_sync_or_async(func, self, *args, **kwargs)

        merged = {
            **(getattr(func, "_handler", {}) or {}),
            "http_method": HttpMethod.SOCKET.value,
            "path": url_path,
            "open_api_spec": False,
            "tags": None,
        }
        # pylint: disable=protected-access
        wrapper._handler = merged  # type: ignore[attr-defined]
        return wrapper

    return cast(_EndpointDecorator, decorator)


def consumes(media_type: MediaType) -> _EndpointDecorator:
    """Decorator indicating what media type the endpoint consumes."""

    def decorator(func: Callable[..., Any]) -> AsyncMethod:
        sig = inspect.signature(func)

        try:
            hints = get_type_hints(func, include_extras=True)
        # pylint: disable-next=W0718
        except Exception:
            hints = getattr(func, "__annotations__", {}) or {}

        consumed_type: Optional[Any] = None
        for name, param in list(sig.parameters.items())[2:]:
            ann = hints.get(name, param.annotation)
            ann = _unwrap_annotated(ann)
            if _is_pydantic_model(ann):
                consumed_type = ann
                break

        @wraps(func)
        async def wrapper(self: Controller, *args: Any, **kwargs: Any) -> "Response":
            # Request is auto-injected as the first arg after self
            if not args:
                raise RuntimeError(
                    "Request must be auto-injected as the first argument after self."
                )
            req: "Request" = args[0]  # type: ignore[index]

            incoming_ct = req.headers.get("content-type", "")
            if not _content_type_matches(incoming_ct, media_type):
                return req.response.json(
                    {
                        "detail": "Unsupported Media Type",
                        "expected": media_type.value,
                        "received": incoming_ct or None,
                    }
                ).status(415)

            payload = await _read_payload_for_consumes(req, media_type)
            # Parameters: [0]=self, [1]=req, others start at index 2
            for name, param in list(sig.parameters.items())[2:]:
                if name in kwargs:
                    continue

                ann = hints.get(name, param.annotation)
                if _is_pydantic_model(ann):
                    kwargs[name] = _build_model(ann, payload)

            return await run_sync_or_async(func, self, *args, **kwargs)

        prev = getattr(func, "_handler", {}) or {}
        merged = dict(prev)
        merged.update({"consumes": media_type, "consumes_type": consumed_type})
        # pylint: disable=protected-access
        wrapper._handler = merged  # type: ignore[attr-defined]
        return wrapper

    return decorator


def produces(
    media_type: MediaType, status_code: HttpStatus = HttpStatus.OK
) -> _EndpointDecorator:
    """
    Decorator indicating what media types the endpoint
    produces and what the default status code is.
    """

    def decorator(func: Callable[..., Any]) -> AsyncMethod:
        expected_body = _extract_response_type(func)

        @wraps(func)
        async def wrapper(self: Controller, *args: Any, **kwargs: Any) -> "Response":
            # Request is auto-injected as first arg after self
            if not args:
                raise RuntimeError(
                    "Request must be auto-injected as the first argument after self."
                )
            req: "Request" = args[0]  # type: ignore[index]
            # pylint: disable=protected-access
            req.response._set_expected_body_type(expected_body)

            res: "Response" = await run_sync_or_async(func, self, *args, **kwargs)
            res.set_header("content-type", media_type.value)
            if status_code != HttpStatus.OK:
                res.status(status_code)
            return res

        # Preserve/merge handler metadata (produces list)
        prev = getattr(func, "_handler", {}) or {}
        merged = dict(prev)
        merged.update({"produces": media_type, "default_status_code": status_code})
        # pylint: disable=protected-access
        wrapper._handler = merged  # type: ignore[attr-defined]
        return wrapper

    return decorator


def open_api_docs(*args: Descriptor):
    """Adds descriptions for error responses to OpenAPI documentation"""

    def decorator(func: AsyncMethod) -> AsyncMethod:
        prev = getattr(func, "_handler", {}) or {}
        merged = dict(prev)
        merged.update({"error_responses": list(args)})
        # pylint: disable=protected-access
        func._handler = merged  # type: ignore[attr-defined]
        return func

    return decorator


def before_request(func: Callable[..., Any]) -> Callable[..., Any]:
    setattr(func, "_before_request", True)
    return func


def after_request(func: Callable[..., Any]) -> Callable[..., Any]:
    setattr(func, "_after_request", True)
    return func


def cors(
    *,
    allow_origins: Optional[list[str]] = None,
    allow_methods: Optional[list[str]] = None,
    allow_headers: Optional[list[str]] = None,
    expose_headers: Optional[list[str]] = None,
    allow_credentials: Optional[bool] = None,
    max_age: Optional[int] = None,
) -> Callable:
    """
    Per-endpoint CORS override. Any provided option overrides the global config.
    Usage:
    ```
        @path("/items")
        @cors(allow_origins=["https://app.example.com"], allow_credentials=True)
        async def list_items(self, req: Request) -> Response: ...
    ```
    """

    def decorator(func: Callable) -> Callable:
        setattr(
            func,
            "_cors_options",
            {
                "allow_origins": allow_origins,
                "allow_methods": allow_methods,
                "allow_headers": allow_headers,
                "expose_headers": expose_headers,
                "allow_credentials": allow_credentials,
                "max_age": max_age,
            },
        )
        return func

    return decorator


def no_cors(func: Callable) -> Callable:
    """
    Decorator to disable CORS for a specific endpoint handler.
    Usage:
    ```
        @path("/internal")
        @no_cors
        async def internal(self, req: Request) -> Response:
            return req.res.text("No CORS here")
    ```
    """
    setattr(func, "_disable_cors", True)
    return func


def development(func_or_cls: Callable | Type[Any]) -> Callable | Type:
    """
    Decorator to mark a controller or endpoint as development only.
    The decorated controller or endpoint will be unreachable if the
    application is not in DEBUG mode.
    """
    setattr(func_or_cls, "_development", True)
    return func_or_cls
