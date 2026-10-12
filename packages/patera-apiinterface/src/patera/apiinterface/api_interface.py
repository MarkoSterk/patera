"""
Interface for declarative external API integrations.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import re
from collections.abc import Mapping
from enum import StrEnum
from functools import wraps
from typing import (
    Any,
    Callable,
    Generic,
    Optional,
    TypeVar,
    cast,
    get_type_hints,
    overload,
)
from urllib.parse import quote

import httpx
from httpx import Response
from pydantic import BaseModel

from patera import (
    BaseExtension,
    HttpMethod,
    MediaType,
    Patera,
    Request,
    UploadedFile,
)
from patera.ctx import current_request, has_request_context


class AuthType(StrEnum):
    BASIC_AUTH = "basic_auth"
    BEARER = "bearer_token"
    API_KEY = "api_key"


F = TypeVar(
    "F",
    bound=Callable[..., Any],
)

DecoratorTargetT = TypeVar(
    "DecoratorTargetT",
    bound=Callable[..., Any] | type[Any],
)

ClassT = TypeVar(
    "ClassT",
    bound=type[Any],
)

AppT = TypeVar(
    "AppT",
    bound="Patera[Any]",
)


_NO_AUTH = object()
_MISSING_BODY = object()

# "<name>" or "<converter:name>" placeholders in resource URLs.
_PLACEHOLDER_RE = re.compile(r"<(?:[^<>:]+:)?(\w+)>")

# Methods whose leftover arguments become query parameters, not a body.
_QUERY_METHODS = frozenset({HttpMethod.GET, HttpMethod.HEAD})


def _set_api_interface_config(
    target: DecoratorTargetT,
    key: str,
    value: Any,
    *,
    allow_class: bool,
) -> DecoratorTargetT:
    """
    Add configuration metadata to an API interface class or method.

    Class-level defaults are stored in __api_interface_defaults__.
    Method-level configuration is stored in __api_interface__.
    """
    if inspect.isclass(target):
        if not allow_class:
            raise TypeError(f"@{key} cannot be applied to a class.")

        configs: dict[str, Any] = dict(
            getattr(
                target,
                "__api_interface_defaults__",
                {},
            )
            or {}
        )

        attribute_name = "__api_interface_defaults__"

    else:
        configs = dict(
            getattr(
                target,
                "__api_interface__",
                {},
            )
            or {}
        )

        attribute_name = "__api_interface__"

    if key == "custom_headers":
        existing_headers = dict(
            configs.get(
                "custom_headers",
                {},
            )
            or {}
        )

        configs[key] = {
            **existing_headers,
            **cast(
                dict[str, Any],
                value,
            ),
        }

    else:
        configs[key] = value

    setattr(
        target,
        attribute_name,
        configs,
    )

    return target


def service(
    service_url: str,
) -> Callable[[ClassT], ClassT]:
    """
    Configure the base URL of an API interface.

    The supplied value can be an application configuration key or a literal
    URL. Application configuration is checked first.

    The exact decorated class type is preserved for static type checking.
    """

    def decorator(
        cls: ClassT,
    ) -> ClassT:
        setattr(
            cls,
            "__service_url__",
            service_url,
        )

        return cls

    return decorator


def method(
    http_method: HttpMethod,
) -> Callable[[F], F]:
    """
    Configure the HTTP method of an API interface method.
    """

    def decorator(
        func: F,
    ) -> F:
        return _set_api_interface_config(
            func,
            "method",
            http_method,
            allow_class=False,
        )

    return decorator


def resource(
    url: str,
    follow_redirects: bool = True,
) -> Callable[[F], F]:
    """
    Configure the remote resource URL of an API interface method.
    """

    def decorator(
        func: F,
    ) -> F:
        configured_func = _set_api_interface_config(
            func,
            "target",
            url,
            allow_class=False,
        )

        return _set_api_interface_config(
            configured_func,
            "follow_redirects",
            follow_redirects,
            allow_class=False,
        )

    return decorator


def consumes(
    media: MediaType,
) -> Callable[[DecoratorTargetT], DecoratorTargetT]:
    """
    Configure the outgoing request media type.

    Can be applied to an API interface class as a default or to an individual
    method as an override.
    """

    def decorator(
        target: DecoratorTargetT,
    ) -> DecoratorTargetT:
        return _set_api_interface_config(
            target,
            "consumes",
            media,
            allow_class=True,
        )

    return decorator


def produces(
    media: MediaType,
) -> Callable[[DecoratorTargetT], DecoratorTargetT]:
    """
    Configure the expected response media type.

    Can be applied to an API interface class as a default or to an individual
    method as an override.
    """

    def decorator(
        target: DecoratorTargetT,
    ) -> DecoratorTargetT:
        return _set_api_interface_config(
            target,
            "produces",
            media,
            allow_class=True,
        )

    return decorator


def headers(
    custom_headers: dict[str, Any],
) -> Callable[[DecoratorTargetT], DecoratorTargetT]:
    """
    Configure custom request headers.

    Class-level and method-level headers are merged. A method-level header
    overrides a class-level header with the same name.
    """

    def decorator(
        target: DecoratorTargetT,
    ) -> DecoratorTargetT:
        return _set_api_interface_config(
            target,
            "custom_headers",
            dict(custom_headers),
            allow_class=True,
        )

    return decorator


def timeout(
    timeout_seconds: int | float,
) -> Callable[[DecoratorTargetT], DecoratorTargetT]:
    """
    Configure the outgoing request timeout.

    Can be applied to an API interface class as a default or to an individual
    method as an override.
    """

    def decorator(
        target: DecoratorTargetT,
    ) -> DecoratorTargetT:
        return _set_api_interface_config(
            target,
            "timeout",
            timeout_seconds,
            allow_class=True,
        )

    return decorator


def auth(
    auth_type: AuthType,
    *,
    username: str | None = None,
    password: str | None = None,
    token: str | None = None,
    api_key: str | None = None,
    header_name: str = "Authorization",
) -> Callable[[DecoratorTargetT], DecoratorTargetT]:
    """
    Configure authentication on an API interface class or method.

    BASIC_AUTH requires username and password.
    BEARER requires token.
    API_KEY requires api_key.

    Credential values can be application configuration keys or literal values.
    Application configuration is checked first.
    """
    if auth_type == AuthType.BASIC_AUTH:
        if username is None or password is None:
            raise ValueError(
                "Basic authentication requires both username and password."
            )

    elif auth_type == AuthType.BEARER:
        if token is None:
            raise ValueError("Bearer authentication requires token.")

    elif auth_type == AuthType.API_KEY:
        if api_key is None:
            raise ValueError("API-key authentication requires api_key.")

    else:
        raise ValueError(f"Unsupported API authentication type: {auth_type!r}")

    auth_config: dict[str, Any] = {
        "type": auth_type,
        "username": username,
        "password": password,
        "token": token,
        "api_key": api_key,
        "header_name": header_name,
    }

    def decorator(
        target: DecoratorTargetT,
    ) -> DecoratorTargetT:
        return _set_api_interface_config(
            target,
            "auth",
            auth_config,
            allow_class=True,
        )

    return decorator


@overload
def forward_request(target: DecoratorTargetT) -> DecoratorTargetT: ...
@overload
def forward_request(
    target: bool = True,
) -> Callable[[DecoratorTargetT], DecoratorTargetT]: ...
def forward_request(
    target: DecoratorTargetT | bool = True,
) -> DecoratorTargetT | Callable[[DecoratorTargetT], DecoratorTargetT]:
    """
    Forward the incoming request's route parameters and query string.

    By default an interface method takes URL placeholders and query
    parameters only from its own arguments. With @forward_request (on the
    class or a method) a call made during a request also uses that request:
    placeholders without a matching argument take the route parameter of the
    same name, and the request's query parameters are sent along, with the
    method's own query arguments taking precedence. Outside a request there
    is nothing to forward. ``@forward_request(False)`` turns a class-level
    setting off for one method.

    Usage:
    ```
        @method(HttpMethod.GET)
        @resource("/items/<item_id>")
        @forward_request
        async def item(self) -> Item: ...
    ```
    """
    if isinstance(target, bool):
        enabled = target

        def decorator(inner: DecoratorTargetT) -> DecoratorTargetT:
            return _set_api_interface_config(
                inner, "forward_request", enabled, allow_class=True
            )

        return decorator

    return _set_api_interface_config(target, "forward_request", True, allow_class=True)


def no_auth(
    func: F,
) -> F:
    """
    Disable inherited class-level authentication for one method.
    """
    return _set_api_interface_config(
        func,
        "auth",
        _NO_AUTH,
        allow_class=False,
    )


class MissingApiInterfaceConfigurations(Exception):
    """
    Raised when required API interface configuration is missing.
    """


class ApiInterfaceResponseError(Exception):
    """
    Raised when the external API answers with a 4xx or 5xx status.

    status_code: the response's status code
    body: the decoded response body (by the method's @produces media type),
        or the raw text if it could not be decoded
    response: the httpx.Response, for headers and anything else

    Annotate a method with ``-> httpx.Response`` to receive every response
    unchecked and handle the status yourself.
    """

    def __init__(self, method_name: str, response: Response, body: Any):
        self.status_code: int = response.status_code
        self.body: Any = body
        self.response: Response = response
        request = response.request
        super().__init__(
            f"{method_name}: {request.method} {request.url} answered "
            f"{response.status_code} {response.reason_phrase}"
        )


class ApiInterface(
    BaseExtension[AppT],
    Generic[AppT],
):
    """
    Base extension for declarative external API integrations.

    A method's arguments fill the ``<name>`` placeholders of its resource URL.
    The remaining arguments become query parameters for GET and HEAD, and the
    request body for other methods. The incoming request is used only when a
    method or class is marked with @forward_request.

    All calls of one interface share one HTTPX client, so connections are
    reused. It is created on first use and closed when the application shuts
    down. Override create_client() to configure it.
    """

    _client: Optional[httpx.AsyncClient] = None
    _client_loop: Optional[asyncio.AbstractEventLoop] = None

    def init(self) -> None:
        service_url = getattr(
            self,
            "__service_url__",
            None,
        )

        if service_url is None:
            raise MissingApiInterfaceConfigurations(
                "Missing service URL for API interface. "
                "Use @service on the interface class."
            )

        self._service_url = self._app.get_conf(
            service_url,
            service_url,
        )
        self._client = None
        self._client_loop = None
        self._app.add_on_shutdown_method(self.aclose)

    def create_client(self) -> httpx.AsyncClient:
        """
        Creates the HTTPX client shared by this interface's calls. Override
        to set connection limits, proxies, a transport or default headers.
        Per-call settings (timeout, redirects, headers) are applied on each
        request.
        """
        return httpx.AsyncClient()

    @property
    def client(self) -> httpx.AsyncClient:
        """
        The shared HTTPX client, created on first use.

        A client belongs to the event loop it was created in. When a call
        runs in another loop (each CLI command, for example, starts one) a
        new client is created for it.
        """
        loop = asyncio.get_running_loop()
        if self._client is None or self._client_loop is not loop:
            self._client = self.create_client()
            self._client_loop = loop
        return self._client

    async def aclose(self) -> None:
        """Closes the shared client. Runs automatically at shutdown."""
        client, self._client, self._client_loop = self._client, None, None
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()

    @classmethod
    def _wrap_method(
        cls,
        func: F,
    ) -> F:
        @wraps(func)
        async def inner(
            self: ApiInterface[Any],
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            return await self._wrapper(
                func,
                *args,
                **kwargs,
            )

        return cast(
            F,
            inner,
        )

    def _get_method_configs(
        self,
        func: Callable[..., Any],
    ) -> dict[str, Any]:
        raw_method_configs: Optional[dict[str, Any]] = getattr(
            func,
            "__api_interface__",
            None,
        )

        if raw_method_configs is None:
            raise MissingApiInterfaceConfigurations(
                f"API interface method {func.__name__} does not have any "
                "configuration. Add at least @resource to the method."
            )

        class_configs: dict[str, Any] = dict(
            getattr(
                type(self),
                "__api_interface_defaults__",
                {},
            )
            or {}
        )

        method_configs = dict(raw_method_configs)

        configs = {
            **class_configs,
            **method_configs,
        }

        class_headers = dict(
            class_configs.get(
                "custom_headers",
                {},
            )
            or {}
        )

        method_headers = dict(
            method_configs.get(
                "custom_headers",
                {},
            )
            or {}
        )

        if class_headers or method_headers:
            configs["custom_headers"] = {
                **class_headers,
                **method_headers,
            }

        if method_configs.get("auth") is _NO_AUTH:
            configs.pop(
                "auth",
                None,
            )

        return configs

    async def _wrapper(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        configs = self._get_method_configs(func)

        target = configs.get("target")

        if target is None:
            raise MissingApiInterfaceConfigurations(
                f"API interface method {func.__name__} is missing @resource."
            )

        # The incoming request is used only when forwarding is enabled.
        req: Optional[Request] = (
            cast(Request, current_request.req)
            if configs.get("forward_request", False) and has_request_context()
            else None
        )
        arguments = self._bind_arguments(func, args, kwargs)

        try:
            return_type = get_type_hints(func).get("return")
        except Exception:
            return_type = None

        # Only the resource path is formatted, never the service URL.
        url = cast(str, self._service_url) + self._format_url(
            func, cast(str, target), arguments, req
        )

        follow_redirects = cast(
            bool,
            configs.get(
                "follow_redirects",
                True,
            ),
        )

        http_method = cast(
            HttpMethod,
            configs.get(
                "method",
                HttpMethod.GET,
            ),
        )

        request_timeout = configs.get(
            "timeout",
            10,
        )

        request_headers = self._construct_headers(configs)

        query_params: dict[str, Any] = (
            dict(req.query_parameters) if req is not None else {}
        )
        if http_method in _QUERY_METHODS:
            query_params.update(self._query_from_arguments(arguments))
            request_body: Any = _MISSING_BODY
        else:
            request_body = self._body_from_arguments(arguments)

        request_options: dict[str, Any] = {
            "headers": request_headers,
            "timeout": request_timeout,
            "follow_redirects": follow_redirects,
        }
        if query_params:
            request_options["params"] = query_params

        if http_method != HttpMethod.GET and request_body is not _MISSING_BODY:
            consumes_media = configs.get(
                "consumes",
                MediaType.APPLICATION_JSON,
            )

            if consumes_media in {
                MediaType.APPLICATION_JSON,
                MediaType.APPLICATION_PROBLEM_JSON,
                MediaType.APPLICATION_X_NDJSON,
            }:
                request_options["json"] = self._prepare_json_body(request_body)

            elif consumes_media == MediaType.MULTIPART_FORM_DATA:
                request_options["files"] = self._get_multipart_parts(request_body)

            else:
                form_data, files = self._get_form_and_files(request_body)

                if form_data is not None:
                    request_options["data"] = form_data

                if files is not None:
                    request_options["files"] = files

        response = await self.client.request(
            http_method,
            url,
            **request_options,
        )

        if return_type is Response:
            # The caller asked for the raw response, status unchecked.
            return response

        produces_media = configs.get("produces", MediaType.APPLICATION_JSON)
        if response.is_error:
            try:
                error_body = self._get_response_body(response, produces_media)
            except ValueError:
                error_body = response.text
            raise ApiInterfaceResponseError(func.__name__, response, error_body)

        response_body = self._get_response_body(response, produces_media)

        if (
            return_type
            and inspect.isclass(return_type)
            and issubclass(
                return_type,
                BaseModel,
            )
        ):
            return return_type.model_validate(response_body)

        return response_body

    def _bind_arguments(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Returns the call's arguments by parameter name, without ``self``.
        Positional and keyword arguments are both supported.
        """
        bound = inspect.signature(func).bind_partial(self, *args, **kwargs)
        arguments = dict(bound.arguments)
        arguments.pop("self", None)
        return arguments

    def _body_from_arguments(self, arguments: dict[str, Any]) -> Any:
        """
        Build the outgoing body from the arguments left after URL
        placeholders were filled.

        No arguments:
            No outgoing body.

        One argument:
            The argument value is used directly as the body.

        Multiple arguments:
            A dictionary is created using the method parameter names.
        """
        if not arguments:
            return _MISSING_BODY

        if len(arguments) == 1:
            return next(iter(arguments.values()))

        return arguments

    def _query_from_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Build query parameters from the arguments left after URL placeholders
        were filled. A single mapping or Pydantic model argument supplies its
        items; otherwise each argument is one parameter. None values are
        left out; lists become repeated parameters.
        """
        values: Mapping[str, Any] = arguments
        if len(arguments) == 1:
            only = next(iter(arguments.values()))
            if isinstance(only, BaseModel):
                values = only.model_dump(mode="json")
            elif isinstance(only, Mapping):
                values = only

        params: dict[str, Any] = {}
        for key, value in values.items():
            if value is None:
                continue
            if isinstance(value, StrEnum):
                value = str(value)
            params[str(key)] = value
        return params

    def _prepare_json_body(
        self,
        value: Any,
    ) -> Any:
        """
        Normalize Pydantic models and verify JSON serializability.
        """
        normalized = self._normalize_json_value(value)

        try:
            json.dumps(normalized)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "API interface request body is not JSON serializable."
            ) from exc

        return normalized

    def _normalize_json_value(
        self,
        value: Any,
    ) -> Any:
        """
        Recursively convert supported values to JSON-compatible structures.
        """
        if isinstance(
            value,
            BaseModel,
        ):
            return value.model_dump(mode="json")

        if isinstance(
            value,
            Mapping,
        ):
            return {
                str(key): self._normalize_json_value(item)
                for key, item in value.items()
            }

        if isinstance(
            value,
            (list, tuple),
        ):
            return [self._normalize_json_value(item) for item in value]

        return value

    def _construct_headers(
        self,
        configs: Optional[dict[str, Any]],
    ) -> dict[str, str]:
        configs = configs or {}

        consumes_media = cast(
            MediaType,
            configs.get(
                "consumes",
                MediaType.APPLICATION_JSON,
            ),
        )

        request_headers: dict[str, str] = {
            "Accept": str(
                configs.get(
                    "produces",
                    MediaType.APPLICATION_JSON,
                )
            ),
            **{
                str(key): str(value)
                for key, value in configs.get(
                    "custom_headers",
                    {},
                ).items()
            },
        }

        if consumes_media == MediaType.MULTIPART_FORM_DATA:
            for header_name in list(request_headers):
                if header_name.lower() == "content-type":
                    request_headers.pop(header_name)
        else:
            request_headers.setdefault(
                "Content-Type",
                str(consumes_media),
            )

        auth_config: Optional[dict[str, Any]] = configs.get("auth")

        if auth_config is not None:
            header_name = cast(
                str,
                auth_config.get(
                    "header_name",
                    "Authorization",
                ),
            )

            request_headers[header_name] = self._create_auth_header(auth_config)

        return request_headers

    def _format_url(
        self,
        func: Callable[..., Any],
        url: str,
        arguments: dict[str, Any],
        req: Optional[Request] = None,
    ) -> str:
        """
        Fills the ``<name>`` placeholders of the URL. Each placeholder takes
        the method argument of the same name, which is then no longer part
        of the body or query. With forwarding enabled, a placeholder without
        an argument takes the incoming request's route parameter. Values are
        percent-encoded. A placeholder without a value raises
        MissingApiInterfaceConfigurations.
        """

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name in arguments:
                value = arguments.pop(name)
            elif req is not None and name in req.route_parameters:
                value = req.route_parameters[name]
            else:
                raise MissingApiInterfaceConfigurations(
                    f"No value for the URL placeholder <{name}> of "
                    f"{func.__name__}. Add a parameter named {name!r} to the "
                    "method, or mark it with @forward_request to use the "
                    "incoming request's route parameter."
                )
            return quote(str(value), safe="")

        return _PLACEHOLDER_RE.sub(replace, url)

    def _get_form_and_files(
        self,
        data: Any,
    ) -> tuple[
        dict[str, Any] | None,
        list[tuple[str, tuple[Any, ...]]] | None,
    ]:
        """
        Split a Pydantic model or mapping into form fields and uploaded files.

        Repeated file fields are preserved as repeated multipart parts.
        """
        if isinstance(data, BaseModel):
            values: Mapping[str, Any] = {
                field_name: getattr(data, field_name)
                for field_name in type(data).model_fields
            }

        elif isinstance(data, Mapping):
            values = {str(key): value for key, value in data.items()}

        else:
            raise TypeError(
                "Non-JSON request bodies must be a Pydantic model or a mapping."
            )

        form_data: dict[str, Any] = {}
        files: list[
            tuple[
                str,
                tuple[Any, ...],
            ]
        ] = []

        for field_name, value in values.items():
            if isinstance(value, UploadedFile):
                files.append(
                    (
                        field_name,
                        (
                            value.filename,
                            value.get_stream(),
                            value.content_type,
                        ),
                    )
                )
                continue

            if isinstance(value, (list, tuple)) and all(
                isinstance(item, UploadedFile) for item in value
            ):
                for uploaded_file in value:
                    files.append(
                        (
                            field_name,
                            (
                                uploaded_file.filename,
                                uploaded_file.get_stream(),
                                uploaded_file.content_type,
                            ),
                        )
                    )

                continue

            form_data[field_name] = value

        return (
            form_data or None,
            files or None,
        )

    def _resolve_auth_value(
        self,
        value: str | None,
    ) -> str | None:
        """
        Resolve an authentication value from application configuration.

        If the configuration key does not exist, the supplied value is used
        literally.
        """
        if value is None:
            return None

        return cast(
            str,
            self._app.get_conf(
                value,
                value,
            ),
        )

    def _create_auth_header(
        self,
        auth_config: dict[str, Any],
    ) -> str:
        auth_type = auth_config.get("type")

        if auth_type == AuthType.BASIC_AUTH:
            username = self._resolve_auth_value(auth_config.get("username"))

            password = self._resolve_auth_value(auth_config.get("password"))

            if username is None or password is None:
                raise ValueError(
                    "Basic authentication requires both username and password."
                )

            credentials = f"{username}:{password}"

            encoded = base64.b64encode(credentials.encode()).decode()

            return f"Basic {encoded}"

        if auth_type == AuthType.BEARER:
            token = self._resolve_auth_value(auth_config.get("token"))

            if token is None:
                raise ValueError("Bearer authentication requires token.")

            return f"Bearer {token}"

        if auth_type == AuthType.API_KEY:
            api_key = self._resolve_auth_value(auth_config.get("api_key"))

            if api_key is None:
                raise ValueError("API-key authentication requires api_key.")

            return api_key

        raise ValueError(f"Unsupported API authentication type: {auth_type!r}")

    def _get_response_body(
        self,
        response: Response,
        media_type: MediaType,
    ) -> Any:
        if media_type in {
            MediaType.APPLICATION_JSON,
            MediaType.APPLICATION_X_NDJSON,
            MediaType.APPLICATION_PROBLEM_JSON,
        }:
            if not response.content:
                # e.g. 204 No Content
                return None
            if media_type == MediaType.APPLICATION_X_NDJSON:
                return [
                    json.loads(line)
                    for line in response.text.splitlines()
                    if line.strip()
                ]
            return response.json()

        if media_type in {
            MediaType.TEXT_CSV,
            MediaType.TEXT_HTML,
            MediaType.TEXT_PLAIN,
            MediaType.TEXT_XML,
            MediaType.TEXT_YAML,
        }:
            return response.text

        return response.read()

    def _get_multipart_parts(
        self,
        data: Any,
    ) -> list[tuple[str, tuple[Any, ...]]]:
        if isinstance(data, BaseModel):
            values: Mapping[str, Any] = {
                field_name: getattr(data, field_name)
                for field_name in type(data).model_fields
            }
        elif isinstance(data, Mapping):
            values = {str(key): value for key, value in data.items()}
        else:
            raise TypeError(
                "Multipart request bodies must be a Pydantic model or a mapping."
            )

        parts: list[tuple[str, tuple[Any, ...]]] = []

        for field_name, value in values.items():
            items = value if isinstance(value, (list, tuple)) else [value]

            for item in items:
                if isinstance(item, UploadedFile):
                    parts.append(
                        (
                            field_name,
                            (
                                item.filename,
                                item.get_stream(),
                                item.content_type,
                            ),
                        )
                    )
                else:
                    parts.append(
                        (
                            field_name,
                            (
                                None,
                                str(item),
                            ),
                        )
                    )

        return parts

    def __init_subclass__(
        cls,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)

        for name, value in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue

            if callable(value) and hasattr(
                value,
                "__api_interface__",
            ):
                setattr(
                    cls,
                    name,
                    ApiInterface._wrap_method(value),
                )
