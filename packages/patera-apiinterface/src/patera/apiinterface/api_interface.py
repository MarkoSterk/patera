"""
Interface for declarative external API integrations.
"""

from __future__ import annotations

import base64
import inspect
import json
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
)

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
from patera.ctx import current_request


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


class ApiInterface(
    BaseExtension[AppT],
    Generic[AppT],
):
    """
    Base extension for declarative external API integrations.

    API interface methods obtain the active Patera Request through
    patera.ctx.current_request.
    """

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

        req = cast(
            Request,
            current_request.req,
        )

        return_type = get_type_hints(func).get("return")

        url = cast(
            str,
            self._service_url,
        ) + cast(
            str,
            target,
        )

        url = self._format_url(
            req,
            url,
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

        request_body = self._extract_request_body(
            func,
            args,
            kwargs,
        )

        request_options: dict[str, Any] = {
            "headers": request_headers,
            "timeout": request_timeout,
            "params": req.query_parameters,
            "follow_redirects": follow_redirects,
        }

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

        async with httpx.AsyncClient() as client:
            response = await client.request(
                http_method,
                url,
                **request_options,
            )

        response_body = self._get_response_body(
            response,
            configs.get(
                "produces",
                MediaType.APPLICATION_JSON,
            ),
        )

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

    def _extract_request_body(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """
        Build the outgoing body from interface method arguments.

        No arguments:
            No outgoing body.

        One argument:
            The argument value is used directly as the body.

        Multiple arguments:
            A dictionary is created using the method parameter names.

        Positional and keyword arguments are both supported.
        """
        signature = inspect.signature(func)

        bound = signature.bind_partial(
            self,
            *args,
            **kwargs,
        )

        arguments = dict(bound.arguments)

        arguments.pop(
            "self",
            None,
        )

        if not arguments:
            return _MISSING_BODY

        if len(arguments) == 1:
            return next(iter(arguments.values()))

        return arguments

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
        req: Request,
        url: str,
    ) -> str:
        for key, value in req.route_parameters.items():
            url = url.replace(
                f"<{key}>",
                str(value),
            )

        return url

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
