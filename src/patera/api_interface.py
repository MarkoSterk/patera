"""
Interface for API integration
"""

import base64
from typing import (
    Callable,
    Dict,
    Any,
    Optional,
    Tuple,
    Type,
    cast,
    get_type_hints,
    TypeVar,
)
import httpx
from httpx import Response
from functools import wraps
from enum import StrEnum
from pydantic import BaseModel
from patera.patera import Patera
from .http_methods import HttpMethod
from .media_types import MediaType
from .base_extension import BaseExtension
from .request import UploadedFile, Request


class AuthType(StrEnum):
    BASIC_AUTH = "basic_auth"
    BEARER = "bearer_token"
    API_KEY = "api_key"


F = TypeVar("F", bound=Callable[..., Any])


def supress():
    raise NotImplementedError()


def service(service_url: str) -> "Callable":
    def decorator(cls: "Type[ApiInterface]") -> "Type[ApiInterface]":
        setattr(cls, "__service_url__", service_url)
        return cls

    return decorator


def method(http_method: HttpMethod) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        api_int: Dict[str, Any] = getattr(func, "__api_interface__", {}) or {}
        api_int["method"] = http_method
        setattr(func, "__api_interface__", api_int)
        return func

    return decorator


def resource(url: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        api_int: Dict[str, Any] = getattr(func, "__api_interface__", {}) or {}
        api_int["target"] = url
        setattr(func, "__api_interface__", api_int)
        return func

    return decorator


def consumes(media: MediaType) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        api_int: Dict[str, Any] = getattr(func, "__api_interface__", {}) or {}
        api_int["consumes"] = media
        setattr(func, "__api_interface__", api_int)
        return func

    return decorator


def produces(media: MediaType) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        api_int: Dict[str, Any] = getattr(func, "__api_interface__", {}) or {}
        api_int["produces"] = media
        setattr(func, "__api_interface__", api_int)
        return func

    return decorator


def headers(custom_headers: Dict[str, Any]) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        api_int: Dict[str, Any] = getattr(func, "__api_interface__", {}) or {}
        api_int["custom_headers"] = custom_headers
        setattr(func, "__api_interface__", api_int)
        return func

    return decorator


def timeout(timeout: int) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        api_int: Dict[str, Any] = getattr(func, "__api_interface__", {}) or {}
        api_int["timeout"] = timeout
        setattr(func, "__api_interface__", api_int)
        return func

    return decorator


def auth(
    auth_type: AuthType,
    *,
    username: str | None = None,
    password: str | None = None,
    header_name: str = "Authorization",
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        api_int: Dict[str, Any] = getattr(func, "__api_interface__", {}) or {}
        api_int["auth"] = {
            "type": auth_type,
            "username": username,
            "password": password,
            "header_name": header_name,
        }
        setattr(func, "__api_interface__", api_int)
        return func

    return decorator


class MissingApiInterfaceConfigurations(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)


class ApiInterface(BaseExtension):
    def __init__(self) -> None:
        self._app: Optional[Patera] = None
        self._service_url = None

    def init_app(self, app: Patera) -> None:
        self._app = app
        serv_url = getattr(self, "__service_url__", None)
        if serv_url is None:
            raise Exception(
                "Missing service url for API Interface. Use @path from api_interface"
            )
        self._service_url = self._app.get_conf(serv_url, serv_url)

    @classmethod
    def _wrap_method(cls, func):
        @wraps(func)
        async def inner(self, req: Request, *args, **kwargs):
            return await self._wrapper(func, req, *args, **kwargs)

        return inner

    async def _wrapper(self, func, req: Request, *args, **kwargs) -> Any:
        raw_configs: Optional[Dict[str, Any]] = getattr(func, "__api_interface__", None)
        if raw_configs is None:
            raise MissingApiInterfaceConfigurations(
                f"API Interface method {func.__name__} does not have any configurations. Please add configuration decorators."
            )
        configs: Dict[str, Any] = dict(raw_configs)
        return_type: Optional[Type[BaseModel]] = get_type_hints(func).get(
            "return", None
        )
        async with httpx.AsyncClient() as client:
            url: str = cast(str, self._service_url) + cast(str, configs.get("target"))
            url = self._format_url(req, url)
            method = configs.get("method", HttpMethod.GET)
            timeout = configs.get("timeout", 10)
            headers: Dict[str, str] = self._construct_headers(configs)
            pydantic_data: list[BaseModel | dict] = list(
                filter(lambda d: isinstance(d, (BaseModel, dict)), list(args))
            )
            data: BaseModel | dict | None = None
            if len(pydantic_data) > 0:
                data = pydantic_data[0]
            res: Response
            if method == HttpMethod.GET:
                res = await client.request(
                    method, url, headers=headers, timeout=timeout
                )
            else:
                if data is None:
                    raise Exception("Missing body for request.")
                if configs.get("consumes", MediaType.APPLICATION_JSON) in [
                    MediaType.APPLICATION_JSON,
                    MediaType.APPLICATION_PROBLEM_JSON,
                    MediaType.APPLICATION_X_NDJSON,
                ]:
                    res = await client.request(
                        method,
                        url,
                        headers=headers,
                        timeout=timeout,
                        json=cast(BaseModel, data).model_dump(),
                    )
                else:
                    if isinstance(data, BaseModel):
                        form, files = self._get_form_and_files(data)
                    else:
                        form = data
                        files = None
                    res = await client.request(
                        method,
                        url,
                        headers=headers,
                        timeout=timeout,
                        data=form,
                        files=files,
                    )

            res = self._get_response_body(
                res, configs.get("produces", MediaType.APPLICATION_JSON)
            )
            if return_type and issubclass(return_type, BaseModel):
                return return_type.model_validate(res)
            return res

    def _construct_headers(self, configs: Optional[Dict[str, Any]]) -> Dict[str, str]:
        if configs is None:
            configs = {}

        headers: Dict[str, str] = {
            "Content-Type": configs.get("consumes", MediaType.APPLICATION_JSON),
            "Accept": configs.get("produces", MediaType.APPLICATION_JSON),
            **configs.get("custom_headers", {}),
        }
        auth: Optional[dict[str, Any]] = configs.get("auth", None)
        if auth is not None:
            header_name = cast(str, auth.get("header_name"))
            headers[header_name] = self._create_auth_headers(auth)
        return headers

    def _format_url(self, req: Request, url: str) -> str:
        for key, value in req.route_parameters.items():
            url = url.replace(f"<{key}>", value)
        return url

    def _get_form_and_files(
        self, data: BaseModel
    ) -> Tuple[dict[str, Any], Optional[dict[str, tuple]]]:
        form_data: dict[str, Any] = {}
        files: dict[str, tuple] = {}
        for field in dir(data):
            if field.startswith("_"):
                continue
            value = getattr(data, field, None)
            if isinstance(value, UploadedFile):
                files[field] = (value.filename, value.get_stream(), value.content_type)
                continue
            form_data[field] = value
        if len(files.keys()) == 0:
            files = cast(dict[str, tuple], None)
        if len(form_data.keys()) == 0:
            form_data = cast(dict[str, Any], None)
        return form_data, files

    def _create_auth_headers(self, auth: dict[str, Any]) -> str:
        auth_type = auth.get("type")
        username = auth.get("username")
        password = auth.get("password")
        if auth_type == AuthType.BASIC_AUTH:
            credentials = f"{username}:{password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return f"Basic {encoded}"
        if auth_type == AuthType.BEARER:
            return f"Bearer {self._app.get_conf(password, password)}"  # type: ignore
        if auth_type == AuthType.API_KEY:
            return f"{self._app.get_conf(password, password)}"  # type: ignore
        return ""

    def _get_response_body(self, res: Response, media_type: MediaType) -> Any:
        if media_type in [
            MediaType.APPLICATION_JSON,
            MediaType.APPLICATION_X_NDJSON,
            MediaType.APPLICATION_PROBLEM_JSON,
        ]:
            return res.json()
        if media_type in [
            MediaType.TEXT_CSV,
            MediaType.TEXT_HTML,
            MediaType.TEXT_PLAIN,
            MediaType.TEXT_XML,
            MediaType.TEXT_YAML,
        ]:
            return res.text
        return res.read()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        for name, value in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue

            if callable(value) and hasattr(value, "__api_interface__"):
                setattr(cls, name, ApiInterface._wrap_method(value))
