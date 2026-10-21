"""
Patera application class
"""

# mypy: check-untyped-defs = True
import importlib
import importlib.metadata
import json
import os
import re
import inspect
import time
from collections.abc import AsyncIterator, Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    cast,
    AsyncIterable,
    Union,
)
import aiofiles
from loguru import logger
from loguru._logger import Logger
from pydantic import BaseModel
from werkzeug.exceptions import NotFound, MethodNotAllowed
from werkzeug.routing import WebsocketMismatch, RequestRedirect

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    select_autoescape,
    StrictUndefined,
    Undefined,
)

from .ctx import current_request, CurrentContextProxy
from .exceptions.http_exceptions import (
    BaseHttpException,
    HtmlAborterException,
    StaticPageNotFound,
)
from .http_statuses import HttpStatus
from .http_methods import HttpMethod
from .request import Request
from .response import Response
from .utilities import (
    get_app_root_path,
    run_sync_or_async,
    wait_for_background_tasks,
    _extract_response_type,
    find_python_files_by_name,
    encode_response_headers,
    pascal_to_upper_snake,
)
from .router import Router
from .static import Static
from .static_pages import StaticPages
from .open_api import OpenAPIController
from .controller import path
from .logger import DefaultLogger
from .ctx import request_context
from .controller import Controller
from .exceptions import ExceptionHandler
from .exceptions.runtime_exceptions import ClientDisconnected
from .configuration_base import BaseConfig
from .middleware import MiddlewareBase, AppCallableType
from .cors.cors_mw import CORSMiddleware
from .cli import CLIController
from .cli.cli_controller import CLICommand
from .logging.logger_config_base import LoggerBase
from .logging.log_files import JsonLogFiles, LogFilesConfig
from .injectable import Injectable
from .serializers import SerializerRegistry
from .response_renderer import ResponseRenderer, ResponseRendererException
from .base_extension import BaseExtension
from .request_record import RequestObserver, RequestRecord

logger.remove()

PATERA_ASCIIART: str = r"""
  _____        _______ ______ _____
 |  __ \ /\   |__   __|  ____|  __ \     /\
 | |__) /  \     | |  | |__  | |__) |   /  \
 |  ___/ /\ \    | |  |  __| |  _  /   / /\ \
 | |  / ____ \   | |  | |____| | \ \  / ____ \
 |_| /_/    \_\  |_|  |______|_|  \_\/_/    \_\
A Fast, Simple, and Productive Python Web Framework

"""


def _installed_version() -> str:
    try:
        return importlib.metadata.version("patera")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover
        return "unknown"


PATERA_VERSION: str = _installed_version()

OPEN_API_VERSION: str = "3.0.3"


def print_startup_message(
    host: str,
    port: int,
    debug_mode: bool,
    *,
    app_name: str = "Application",
    scheme: str = "http",
    url_prefix: str = "",
) -> None:
    url = f"{scheme}://{host}:{port}{url_prefix}"

    mode_label = "DEVELOPMENT" if debug_mode else "PRODUCTION"

    print()
    print("═" * 64)
    print(f"  {app_name} is running")
    print("─" * 64)
    print(f"  Mode:    {mode_label}")
    print(f"  Host:    {host}")
    print(f"  Port:    {port}")
    print(f"  URL:     \033]8;;{url}\033\\{url}\033]8;;\033\\")
    print("═" * 64)
    print()


T = TypeVar("T", bound="Patera[Any]")
ConfT = TypeVar("ConfT", bound=BaseConfig)
ExtT = TypeVar("ExtT", bound=Injectable)


def app(import_name: str, configs: Type[ConfT]) -> Callable[[Type[T]], Type[T]]:
    def decorator(cls: Type[T]) -> Type[T]:
        setattr(cls, "_app_configs", {"import_name": import_name, "configs": configs})
        setattr(cls, "_is_patera_app", True)
        return cls

    return decorator


def on_startup(func: Callable) -> Callable:
    """
    Decorated methods will run in alphabetical order on app startup
    """
    setattr(func, "_on_startup_method", True)
    return func


def on_shutdown(func: Callable) -> Callable:
    """
    Decorated methods will run in alphabetical order on app shutdown
    """
    setattr(func, "_on_shutdown_method", True)
    return func


class ScopeType(StrEnum):
    LIFESPAN = "lifespan"
    HTTP = "http"
    WEBSOCKET = "websocket"


class MissingAppConfigurations(Exception):
    def __init__(
        self,
        msg: str = (
            "Missing application configurations. "
            "Decorate the application class with "
            "@app(__name__, configs=YourConfig)."
        ),
    ):
        super().__init__(msg)


def validate_config(config_type: type[ConfT]) -> ConfT:
    if not inspect.isclass(config_type) or not issubclass(config_type, BaseConfig):
        raise MissingAppConfigurations(
            "Configs must be a subclass of patera.BaseConfig."
        )

    try:
        config_factory = cast(Callable[[], ConfT], config_type)
        return config_factory()
    except Exception as e:
        raise MissingAppConfigurations(
            f"Could not instantiate config class {config_type.__name__}: {e}"
        ) from e


class Patera(Injectable, Generic[ConfT]):
    """Patera class implementation. Used to create a new application instance"""

    app_extensions: list[Type[BaseExtension[Any, Any]]] = []

    def __init__(self, cli_mode: bool = False):
        """Init function"""
        app_configs = getattr(self.__class__, "_app_configs", None)

        if app_configs is None:
            raise MissingAppConfigurations()

        import_name = cast(str, app_configs.get("import_name"))
        config_type = cast(type[ConfT], app_configs.get("configs"))

        if not inspect.isclass(config_type) or not issubclass(config_type, BaseConfig):
            raise MissingAppConfigurations(
                "Missing valid configs object in @app(...). "
                "Configuration class must inherit from patera.BaseConfig"
            )
        self._cli_mode = cli_mode
        self._is_built: bool = False
        self._root_path: str = get_app_root_path(import_name)
        self._configs: ConfT = validate_config(cast(type[ConfT], config_type))

        static_dir = self._configs.STATIC_DIR.lstrip("/\\")
        self._static_files_path: str = os.path.join(self._root_path, static_dir)

        self._templates_path: str = os.path.join(
            self._root_path,
            self._configs.TEMPLATES_DIR.lstrip("/\\"),
        )

        self._all_templates_paths: list[str] = []

        self._url_for_alias: dict[str, str] = {
            self._configs.STATIC_CONTROLLER_NAME: "Static.get"
        }

        self._logger_sink_ids: list[int] = []
        # Loggers whose sinks are attached now and again at every startup
        # (shutdown removes them).
        self._loggers: list[LoggerBase] = []
        self._registered_loggers: set[type] = set()

        self._jinja_environment: Environment = Environment(
            loader=None,
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined if self._configs.TEMPLATES_STRICT else Undefined,
            auto_reload=self._configs.AUTO_RELOAD,
            enable_async=True,
        )

        self.response_serializers: SerializerRegistry = SerializerRegistry()
        self.response_serializers.register_defaults()

        self.response_renderer: ResponseRenderer = ResponseRenderer(
            self.response_serializers,
            self,
        )

        default_logger = DefaultLogger(self)
        self._loggers.append(default_logger)
        self._logger_sink_ids.append(default_logger.configure())

        self._router: Router = Router(self._configs.STRICT_SLASHES)
        self._socket_router: Router = Router(self._configs.STRICT_SLASHES)
        self._logger: Logger = cast(Logger, logger)

        log_files_conf: Any = self._configs.LOG_FILES
        if isinstance(log_files_conf, BaseModel):
            log_files_conf = log_files_conf.model_dump()
        self.log_files: JsonLogFiles = JsonLogFiles(
            LogFilesConfig.model_validate(log_files_conf or {}),
            self._root_path,
            default_logger_name=default_logger.logger_name,
        )
        log_files_sink_id = self.log_files.attach()
        if log_files_sink_id is not None:
            self._logger_sink_ids.append(log_files_sink_id)

        self._app: AppCallableType = self._base_app

        # Middleware classes are registered here and instantiated only in build().
        # This keeps CLI mode lightweight while still allowing extensions to
        # register middleware during app initialization.
        self._middleware_classes: dict[int, Type[MiddlewareBase]] = {}
        self._cors_middleware: Optional[CORSMiddleware] = None
        self._request_observers: list[RequestObserver] = []

        self._controllers: dict[str, "Controller"] = {}
        self._cli_controllers: dict[str, "CLIController"] = {}
        self._exception_handlers: dict[type[BaseException], Callable] = {}
        self._exception_handler_instances: dict[str, ExceptionHandler] = {}
        self._json_spec: Optional[dict] = None

        self._extensions: dict[str, Injectable] = {}

        self._on_startup_methods: list[Callable] = []
        self._on_shutdown_methods: list[Callable] = []

        self._get_startup_methods()
        self._get_shutdown_methods()

        # Template lookup: the app's own templates folder comes first so that
        # templates added later (static pages, extensions) can never shadow
        # them. The loader shares the paths list, so paths added later on are
        # picked up as well. Prefixed loaders give components a private
        # namespace ("<prefix>/<template>").
        self.add_template_path(self._templates_path)
        self._template_prefix_loaders: dict[str, BaseLoader] = {}
        file_system_loader = FileSystemLoader([])
        file_system_loader.searchpath = self._all_templates_paths
        self._jinja_environment.loader = ChoiceLoader(
            [file_system_loader, PrefixLoader(self._template_prefix_loaders)]
        )

        self.register_static_pages_controller(self.configs.STATIC_PAGES_URL)
        self.register_static_controller(self.configs.STATIC_URL)

        self._load_controllers_exc_handlers_middleware(cli_mode)
        self._register_app_extensions()
        self._resolve_injections()

        self.register_openapi_controller()
        if not cli_mode:
            self._enable_cors()

    def _load_controllers_exc_handlers_middleware(self, cli_mode: bool = False) -> None:
        logger_folders: list[str] = ["logging", "loggers"]
        logger_folders.extend(self._configs.LOGGER_FOLDERS or [])

        self._load_detected_modules_once(
            logger_folders,
            ["logger", "log_sink", "logging"],
            LoggerBase,
        )

        cli_controller_folders: list[str] = ["cli", "cli_controllers", "clis"]
        cli_controller_folders.extend(self._configs.CLI_CONTROLLER_FOLDERS or [])

        self._load_detected_modules_once(
            cli_controller_folders,
            ["cli", "cli_controller"],
            CLIController,
        )

        if cli_mode:
            return

        controller_folders: list[str] = [
            "api",
            "public",
            "controllers",
            "routers",
            "routes",
        ]
        controller_folders.extend(self._configs.CONTROLLER_FOLDERS or [])

        self._load_detected_modules_once(
            controller_folders,
            ["api", "controller", "public", "router", "routes"],
            Controller,
        )

        exception_handler_folders: list[str] = ["exceptions", "exc_controllers"]
        exception_handler_folders.extend(self._configs.EXCEPTION_HANDLER_FOLDERS or [])

        self._load_detected_modules_once(
            exception_handler_folders,
            ["handler", "exception_controller", "controller"],
            ExceptionHandler,
        )

        middleware_folders: list[str] = ["middleware", "middlewares"]
        middleware_folders.extend(self._configs.MIDDLEWARE_FOLDERS or [])

        self._load_detected_modules_once(
            middleware_folders,
            ["middleware", "mw"],
            MiddlewareBase,
        )

    def _unique_list(self, values: list[str]) -> list[str]:
        """
        Returns a list with duplicates removed while preserving order.
        """
        return list(dict.fromkeys(values))

    def _load_detected_modules_once(
        self,
        folders: list[str],
        name_patterns: list[str],
        load_class: Type,
    ) -> None:
        """
        Scans folders for matching Python files and loads each discovered file only once.
        This protects against duplicate default/configured folders and overlapping scans.
        """
        app_root: Path = Path(self._root_path)
        loaded_files: set[Path] = set()

        for folder in self._unique_list(folders):
            folder_path = app_root / folder
            files = find_python_files_by_name(folder_path, name_patterns)

            unique_files: list[Path] = []
            for file in files:
                resolved_file = file.resolve()
                if resolved_file in loaded_files:
                    continue
                loaded_files.add(resolved_file)
                unique_files.append(file)
            self._load_detected_module(unique_files, load_class)

    def _load_detected_module(self, file_paths: List[Path], load_class: Type) -> None:
        """
        Tries to load implementations:
            - controllers
            - CLI controllers
            - exception handlers
            - middleware
            - loggers
        """
        app_root = Path(self._root_path)
        root_package = app_root.name
        for file_path in file_paths:
            relative_path = file_path.relative_to(app_root)
            module_path = relative_path.with_suffix("")
            import_path = f"{root_package}.{'.'.join(module_path.parts)}"

            module = importlib.import_module(import_path)

            for _, obj in inspect.getmembers(
                module,
                lambda _obj: inspect.isclass(_obj) and issubclass(_obj, load_class),
            ):
                ignore: bool = getattr(obj, "_ignore", False)
                dev_only: bool = getattr(obj, "_development", False)

                if ignore or (dev_only and not self._configs.DEBUG):
                    continue

                if (
                    issubclass(obj, Controller)
                    and obj is not Controller
                    and getattr(obj, "_controller_path", None) is not None
                ):
                    self.register_controller(obj)
                    continue

                if (
                    issubclass(obj, CLIController)
                    and obj is not CLIController
                    and getattr(obj, "_cli_controller", False)
                ):
                    obj_inst = obj(self)
                    self.register_cli_controller(obj_inst)
                    continue

                if (
                    issubclass(obj, MiddlewareBase)
                    and obj is not MiddlewareBase
                    and getattr(obj, "_middleware", False)
                ):
                    self.register_middleware(obj)
                    continue

                if (
                    issubclass(obj, ExceptionHandler)
                    and obj is not ExceptionHandler
                    and getattr(obj, "_exc_handler", False)
                ):
                    self.register_exception_handler(obj)
                    continue

                if (
                    issubclass(obj, LoggerBase)
                    and obj is not LoggerBase
                    and getattr(obj, "_logger", False)
                ):
                    # A logger class imported into a second module must not
                    # add a second sink.
                    if obj in self._registered_loggers:
                        continue
                    self._registered_loggers.add(obj)
                    self.logger.info(f"Registering logger sink: {obj.__name__}")
                    logger_component = obj(self)
                    self._loggers.append(logger_component)
                    self._logger_sink_ids.append(logger_component.configure())
                    continue

    def _enable_cors(self) -> None:
        cors_enabled: bool = self._configs.CORS_ENABLED

        if not cors_enabled:
            return

        self.register_middleware(CORSMiddleware)

    def _marked_methods(self, marker: str) -> list[Callable]:
        """
        Returns bound methods carrying the given decorator marker, sorted by
        name. Properties are skipped so that scanning has no side effects.
        """
        methods = []

        for name in dir(type(self)):
            if isinstance(inspect.getattr_static(self, name, None), property):
                continue

            method = getattr(self, name, None)

            if callable(method) and getattr(method, marker, False):
                methods.append((name, method))

        methods.sort(key=lambda x: x[0])
        return [m for _, m in methods]

    def _get_startup_methods(self) -> None:
        self._on_startup_methods = self._marked_methods("_on_startup_method")

    def _get_shutdown_methods(self) -> None:
        self._on_shutdown_methods = self._marked_methods("_on_shutdown_method")

    def get_conf(self, config_name: str, default: Any = None) -> Any:
        """
        Returns app configuration with provided config_name.

        Dotted names ("DATABASE.URI") read nested attributes or mapping keys.
        Returns ``default`` if the configuration is missing or None.
        """
        if config_name and "." in config_name:
            return self._get_nested_config(config_name, default)

        value = getattr(self._configs, config_name, default)

        if value is None:
            return default

        return value

    def _get_nested_config(self, config_name: str, default: Any = None) -> Any:
        names: list[str] = config_name.split(".")

        first_name = names.pop(0)
        last_name = names.pop()

        config = self.get_conf(first_name)

        if config is None:
            return default

        for name in names:
            config = self._get_config_member(config, name)

            if config is None:
                return default

        value = self._get_config_member(config, last_name)

        if value is None:
            return default

        return value

    @staticmethod
    def _get_config_member(config: Any, name: str) -> Any:
        """Reads a member of a nested config object or mapping."""
        if isinstance(config, dict):
            return config.get(name)
        return getattr(config, name, None)

    async def _base_app(self, req: Request) -> Response:
        """
        The bare-bones application without any middleware.
        Calls the route handler directly.
        """
        if req.automatic_options is not None:
            # OPTIONS request for a route that has no explicit OPTIONS handler.
            # CORS preflights are answered by the CORS middleware before this.
            return req.res.no_content().set_header(
                "allow", ", ".join(req.automatic_options)
            )

        if req.response.expected_body_type() is None:
            expected = _extract_response_type(req.route_handler)
            req.response._set_expected_body_type(expected)

        res: Response = await req.route_handler.__self__(req.route_handler, req)  # type: ignore

        # Convert the body through its Response[Model] type now, inside the
        # middleware chain: the database middleware commits or rolls back and
        # closes the request's sessions on the way out, which expires ORM
        # objects that the body still refers to.
        if isinstance(res, Response):
            self.response_renderer.materialize_body(
                res, req.response.expected_body_type()
            )

        return res

    async def _send_error(
        self,
        send,
        status_code: int,
        message: str,
        data: Any = None,
        headers: Optional[list[tuple[bytes, bytes]]] = None,
    ) -> None:
        """
        Sends a JSON error response straight to the ASGI ``send`` channel.

        Used for errors raised before a request object exists (routing
        failures). The body has the same shape as every other framework
        error: ``status``, ``message`` and, when there is more to say,
        ``data``.
        """
        payload: dict[str, Any] = {"status": "error", "message": message}
        if data is not None:
            payload["data"] = data
        body = json.dumps(payload).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": int(status_code),
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    *(headers or []),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def abort_route_not_found(self, send):
        """
        Aborts request because route was not found.
        """
        await self._send_error(send, HttpStatus.NOT_FOUND, "Endpoint not found")

    async def abort_method_not_allowed(
        self,
        send,
        allowed_methods: list[str],
    ):
        """
        Aborts request because method is not allowed.
        """
        await self._send_error(
            send,
            HttpStatus.METHOD_NOT_ALLOWED,
            "Method not allowed",
            data={"allowed_methods": allowed_methods},
            headers=[(b"allow", ", ".join(allowed_methods).encode("latin-1"))],
        )

    async def abort_bad_request(self, send) -> None:
        """
        Send a 400 Bad Request response.
        """
        await self._send_error(send, HttpStatus.BAD_REQUEST, "Bad request")

    async def redirect_request(
        self,
        send,
        location: str,
        status_code: int,
    ) -> None:
        """
        Send an HTTP redirect response.
        """
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"location", location.encode("latin-1")),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"",
            }
        )

    def _routing_error_send(self, scope: dict, send: Callable) -> Callable:
        """
        Returns the send channel for responses produced by the router
        (404, 405, 400 and trailing-slash redirects).

        These responses are sent before any middleware runs, so the CORS
        middleware never sees them. When CORS is enabled, the global CORS
        settings are applied here instead, so a browser can read the error.
        """
        cors = self._cors_middleware
        if cors is None:
            return send
        return cors.wrap_send_without_route(scope, send)

    async def _iterate_stream(
        self,
        iterable: Union[AsyncIterable[bytes], Iterable[bytes]],
    ) -> AsyncIterator[bytes]:
        """
        Normalizes async/sync iterables into an async iterator of bytes.
        Accepts bytes/bytearray/str chunks and encodes/normalizes to bytes.
        """

        async def _aiter_from_sync(sync_iter: Iterable[bytes]) -> AsyncIterator[bytes]:
            for chunk in sync_iter:
                yield self._normalize_chunk(chunk)

        if hasattr(iterable, "__aiter__"):
            async for chunk in iterable:  # type: ignore[attr-defined]
                yield self._normalize_chunk(chunk)
        else:
            async for chunk in _aiter_from_sync(iterable):  # type: ignore[arg-type]
                yield chunk

    def _normalize_chunk(self, chunk: Any) -> bytes:
        if isinstance(chunk, (bytes, bytearray)):
            return bytes(chunk)

        if isinstance(chunk, str):
            return chunk.encode("utf-8")

        raise TypeError(
            f"Streaming chunks must be bytes, bytearray or str, got {type(chunk)!r}"
        )

    async def send_response(
        self,
        res: Response,
        send,
        response_type: Optional[Type[Any]] = None,
    ):
        """
        Sends response.

        Serialization is delegated to the response renderer / serializer registry.
        This method focuses on transport concerns:
            - zero-copy responses
            - streaming responses
            - normal ASGI start/body sending
        """
        self.response_renderer.apply_default_content_type(res)
        self._log_response(res.request, res.status_code)

        # HEAD responses carry the headers of the equivalent GET response
        # but must never include a body.
        is_head = res.request.method == HttpMethod.HEAD.value

        if res.zero_copy is not None:
            params = res.zero_copy
            file_path = params["file_path"]
            start = params["start"]
            length = params["length"]

            self.response_renderer.finalize_headers(
                res,
                body_bytes=None,
                is_streaming=True,
            )
            # The exact length of a file/range response is known up-front.
            res.headers["content-length"] = str(length)

            await send(
                {
                    "type": "http.response.start",
                    "status": int(res.status_code),
                    "headers": encode_response_headers(res),
                }
            )

            if is_head or length <= 0:
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
                return

            chunk_size = 1 * 1024 * 1024
            remaining = length

            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)

                while remaining > 0:
                    to_read = min(remaining, chunk_size)
                    chunk = await f.read(to_read)

                    if not chunk:
                        # The file shrank while it was being sent; end the
                        # body so the client is not left waiting.
                        await send(
                            {
                                "type": "http.response.body",
                                "body": b"",
                                "more_body": False,
                            }
                        )
                        break

                    remaining -= len(chunk)

                    await send(
                        {
                            "type": "http.response.body",
                            "body": chunk,
                            "more_body": remaining > 0,
                        }
                    )

            return

        if res.is_streaming:
            self.response_renderer.finalize_headers(
                res,
                body_bytes=None,
                is_streaming=True,
            )

            await send(
                {
                    "type": "http.response.start",
                    "status": int(res.status_code),
                    "headers": encode_response_headers(res),
                }
            )

            stream_iter = res.stream_iterable

            if stream_iter is None or is_head:
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                        "more_body": False,
                    }
                )
                return

            async for chunk in self._iterate_stream(stream_iter):
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )

            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )
            return

        body_bytes = await self.response_renderer.render_body(res, response_type)

        self.response_renderer.finalize_headers(
            res,
            body_bytes=body_bytes,
            is_streaming=False,
        )
        await send(
            {
                "type": "http.response.start",
                "status": int(res.status_code),
                "headers": encode_response_headers(res),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"" if is_head else (body_bytes or b""),
                "more_body": False,
            }
        )

    async def _lifespan_app(self, _, receive, send):
        """
        Handles the ASGI lifespan protocol. Startup actions run on
        ``lifespan.startup`` and shutdown actions on ``lifespan.shutdown``.
        A failing action is logged and reported to the server with
        ``lifespan.startup.failed`` or ``lifespan.shutdown.failed``.
        """
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                # A second lifespan (another test client, say) logs again.
                self._attach_logger_sinks()
                try:
                    for method in self._on_startup_methods:
                        await run_sync_or_async(method)
                except Exception as exc:
                    # Report the failure to the server instead of leaving it
                    # waiting for a startup.complete that never arrives.
                    self.logger.exception(exc)
                    await send(
                        {"type": "lifespan.startup.failed", "message": repr(exc)}
                    )
                    return

                await send({"type": "lifespan.startup.complete"})

            elif message["type"] == "lifespan.shutdown":
                try:
                    await self._finish_background_tasks()
                    for method in self._on_shutdown_methods:
                        await run_sync_or_async(method)
                except Exception as exc:
                    self.logger.exception(exc)
                    self._remove_logger_sinks()
                    await send(
                        {"type": "lifespan.shutdown.failed", "message": repr(exc)}
                    )
                    return

                self._remove_logger_sinks()

                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _finish_background_tasks(self) -> None:
        """
        Lets tasks from run_in_background() (emails, task manager jobs, ...)
        finish before shutdown methods close the resources they use.
        """
        timeout = self.configs.BACKGROUND_TASKS_SHUTDOWN_TIMEOUT
        finished, cancelled = await wait_for_background_tasks(timeout)
        if finished:
            self.logger.info(f"Finished {finished} background task(s) before shutdown")
        if cancelled:
            self.logger.warning(
                f"Cancelled {cancelled} background task(s) still running after "
                f"{timeout} seconds (BACKGROUND_TASKS_SHUTDOWN_TIMEOUT)"
            )

    def _attach_logger_sinks(self) -> None:
        """
        Attaches the loggers' sinks and the log files again after a shutdown
        removed them. Does nothing while they are attached.
        """
        if self._logger_sink_ids:
            return
        for logger_component in self._loggers:
            self._logger_sink_ids.append(logger_component.configure())
        log_files_sink_id = self.log_files.attach()
        if log_files_sink_id is not None:
            self._logger_sink_ids.append(log_files_sink_id)

    def _remove_logger_sinks(self) -> None:
        """Removes all logger sinks registered by this application."""
        for logger_sink_id in self._logger_sink_ids:
            try:
                self.logger.remove(logger_sink_id)
            except ValueError:
                # Sink was already removed.
                pass
        self._logger_sink_ids.clear()
        self.log_files.detach()

    def add_request_observer(self, observer: RequestObserver) -> None:
        """
        Calls ``observer(record)`` with a ``RequestRecord`` after every HTTP
        request, including those answered by the router (404, 405), static
        resources and failed requests. Observers run in the request's task
        once its response has been sent, so they must be quick and must not
        block; an observer that raises is logged and skipped.
        """
        self._request_observers.append(observer)

    async def _handle_http_request(self, scope, receive, send):
        """
        Handles HTTP requests, and reports each one to the request observers.
        """
        if not self._request_observers:
            return await self._dispatch_http_request(scope, receive, send)

        started_at = time.time()
        start = time.perf_counter()
        status: list[int] = []

        async def observed_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                status.append(message["status"])
            await send(message)

        failed = False
        try:
            return await self._dispatch_http_request(scope, receive, observed_send)
        except BaseException:
            failed = True
            raise
        finally:
            self._notify_request_observers(
                RequestRecord(
                    method=scope["method"].upper(),
                    path=scope["path"],
                    route=scope.get("patera.route"),
                    status_code=status[0] if status else (500 if failed else None),
                    started_at=started_at,
                    duration=time.perf_counter() - start,
                )
            )

    def _notify_request_observers(self, record: RequestRecord) -> None:
        for observer in self._request_observers:
            try:
                observer(record)
            except Exception as exc:  # an observer must not break requests
                self.logger.error(f"Request observer {observer!r} failed: {exc}")

    async def _dispatch_http_request(self, scope, receive, send):
        """
        Routes an HTTP request and sends its response.
        """
        method: str = scope["method"].upper()
        url_path: str = scope["path"]

        self._log_request(scope, method, url_path)

        route_handler: Optional[Callable] = None
        path_kwargs: Mapping[str, Any] = {}
        automatic_options: Optional[list[str]] = None

        try:
            route_handler, path_kwargs = self.router.match(
                url_path,
                method,
            )
        except NotFound:
            self.logger.info(f"Path {url_path} does not exist")
            return await self.abort_route_not_found(
                self._routing_error_send(scope, send)
            )
        except MethodNotAllowed as exc:
            matching_methods = list(exc.valid_methods or [])

            if method == "OPTIONS" and matching_methods:
                # No explicit OPTIONS handler: resolve the route through one of
                # its real methods so middleware (CORS preflight) can run, and
                # answer with an automatic "Allow" response otherwise.
                route_handler, path_kwargs, automatic_options = (
                    self._match_automatic_options(scope, url_path, matching_methods)
                )
            else:
                self.logger.warning(
                    f"Method {method} not allowed for path {url_path}. "
                    f"Matching methods: {matching_methods}"
                )
                return await self.abort_method_not_allowed(
                    self._routing_error_send(scope, send),
                    matching_methods,
                )
        except WebsocketMismatch:
            self.logger.warning(
                f"Protocol mismatch for path {url_path}: "
                f"HTTP request matched a WebSocket route"
            )
            return await self.abort_bad_request(self._routing_error_send(scope, send))

        except RequestRedirect as exc:
            self.logger.debug(f"Redirecting path {url_path} to {exc.new_url}")
            return await self.redirect_request(
                self._routing_error_send(scope, send),
                exc.new_url,
                exc.code,  # type: ignore
            )

        if self._request_observers:
            scope["patera.route"] = self.router.path_of(cast(Callable, route_handler))

        req = self.request_class(
            scope,
            receive,
            send,
            self,
            cast(dict, path_kwargs),
            cast(Callable, route_handler),
        )
        req.automatic_options = automatic_options

        # All responses are sent through req.send so that middleware which
        # wraps the send channel (e.g. CORS) also applies to error responses.
        try:
            with request_context(
                app=self,
                request=req,
                controller=route_handler.__self__,  # type: ignore
            ):
                try:
                    if bool(
                        getattr(route_handler.__self__, "_static_resource", False)  # type: ignore
                        or getattr(route_handler, "_static_resource", False)
                    ):
                        res: Response = await self._base_app(req)
                        return await self.send_response(res, req.send)

                    res = await self._app(req)

                    if not isinstance(res, Response):
                        raise TypeError(
                            "Return object of request handlers must be an instance "
                            f"of Response, got {type(res).__name__}"
                        )

                    response_type: Optional[Type[Any]] = (
                        req.response.expected_body_type()
                    )

                    return await self.send_response(res, req.send, response_type)

                except Exception as exc:
                    if req.response_started or isinstance(exc, ClientDisconnected):
                        raise
                    return await self._send_exception_response(req, exc)

        except Exception as exc:
            if isinstance(exc, ClientDisconnected):
                # Nobody is left to receive a response.
                self.logger.info(f"({req.method}) {req.path}: {exc}")
                return

            if req.response_started:
                # The status and headers are already out, so the error cannot
                # be answered any more. Raising lets the server close the
                # connection: the client sees an incomplete response rather
                # than one that looks complete.
                self.logger.error(
                    f"Error after the response started: ({req.method}) {req.path}. "
                    "The connection is closed."
                )
                self.logger.exception(exc)
                raise

            req.res.reset()

            if not self.configs.DEBUG:
                res = req.res.json(
                    {
                        "status": "error",
                        "message": "Internal server error",
                    }
                ).status(HttpStatus.INTERNAL_SERVER_ERROR)

                self.logger.critical(
                    f"Unhandled critical error: ({req.method}) {req.path}, "
                    f"{req.route_parameters}"
                )
                self.logger.exception(exc)

                return await self.send_response(res, req.send, None)

            raise

    async def _send_exception_response(self, req: Request, exc: Exception) -> None:
        """
        Answers an exception raised before the response started, with the
        application's handler for it or with the default response. An
        exception without either is raised again, as an unhandled error.
        """
        req.res.reset()

        if isinstance(exc, ResponseRendererException):
            raise exc

        if isinstance(exc, HtmlAborterException):
            handler = self._find_exception_handler(exc, stop_at=HtmlAborterException)
            if handler is None:
                res = (await req.res.html(exc.template, context=exc.data)).status(
                    exc.status_code
                )
                return await self.send_response(res, req.send, None)
        elif isinstance(exc, StaticPageNotFound):
            # A static page that does not exist is a normal 404 - Not Found,
            # unless the application handles StaticPageNotFound itself.
            handler = self._find_exception_handler(exc, stop_at=StaticPageNotFound)
            if handler is None:
                return await self.abort_route_not_found(req.send)
        else:
            handler = self._find_exception_handler(exc)

        if handler is not None:
            res = await run_sync_or_async(handler, req, exc)
        else:
            default_res = self.default_exception_response(req, exc)
            if default_res is None:
                raise exc
            res = default_res

        return await self.send_response(res, req.send, res.expected_body_type())

    async def _close_context_sessions(self, ctx: Any) -> None:
        """
        Closes database sessions a WebSocket handler opened through the
        request context (Model.query(), repositories). HTTP requests have
        the database middleware for that; sockets do not. Work that was not
        committed explicitly is rolled back by the close.
        """
        sessions = ctx.sessions
        if sessions is None:
            return
        for session in list(sessions.sessions.values()):
            try:
                await session.close()
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.exception(exc)
        ctx.sessions = None

    def _match_automatic_options(
        self,
        scope: dict,
        url_path: str,
        allowed_methods: list[str],
    ) -> tuple[Callable, Any, list[str]]:
        """
        Resolves the route handler used to answer an OPTIONS request for a
        route without an explicit OPTIONS handler.
        """
        requested_method: str = ""
        for key, value in scope.get("headers", []):
            if key.lower() == b"access-control-request-method":
                requested_method = value.decode("latin-1").strip().upper()
                break

        match_method = (
            requested_method
            if requested_method in allowed_methods
            else allowed_methods[0]
        )
        route_handler, path_kwargs = self.router.match(url_path, match_method)
        allow = sorted({*allowed_methods, "OPTIONS"})
        return cast(Callable, route_handler), path_kwargs, allow

    def _find_exception_handler(
        self,
        exc: BaseException,
        stop_at: Optional[type[BaseException]] = None,
    ) -> Optional[Callable]:
        """
        Returns the registered handler for the exception.

        The exception class hierarchy is walked so that a handler registered
        for a base class (e.g. BaseHttpException) also handles subclasses.
        The most specific handler wins. Handlers are keyed by class, so two
        exception classes that share a name never share a handler.

        ``stop_at`` ends the walk at that class: exceptions with built-in
        handling (html_abort, missing static pages) can be customized by a
        handler for their own class, but are not captured by handlers for
        generic bases such as BaseHttpException.
        """
        for exc_cls in type(exc).__mro__:
            handler = self._exception_handlers.get(exc_cls)
            if handler is not None:
                return handler
            if exc_cls is stop_at:
                break
        return None

    def default_exception_response(
        self, req: Request, exc: Exception
    ) -> Optional[Response]:
        """
        Fallback responses for exceptions without a registered handler.

        BaseHttpException subclasses (abort(), RequestValidationError from
        @consumes, auth exceptions, ...) become a JSON response with the
        exception's status code.

        Returns None for any other exception, which is then treated as an
        unhandled error (500). That includes a Pydantic ValidationError
        raised outside request-body validation: it is the server's data that
        failed. Override in the app class to customize.
        """
        if isinstance(exc, BaseHttpException):
            return req.res.json(
                {
                    "status": exc.status,
                    "message": exc.message,
                    "data": exc.data,
                }
            ).status(exc.status_code)

        return None

    def _log_request(self, scope, method: str, url_path: str) -> None:
        """
        Logs incoming request.
        """
        self.logger.info(
            "HTTP request. "
            f"CLIENT: {(scope.get('client') or ('-', ''))[0]}, "
            f"SCHEME: {scope['scheme']}, "
            f"METHOD: {method}, "
            f"PATH: {url_path}, "
            f"QUERY_STRING: {scope['query_string'].decode('utf-8', 'replace')}"
        )

    def _log_response(self, req: Request, status_code: int) -> None:
        """
        Logs outgoing response.
        """
        self.logger.info(
            "HTTP response. "
            f"CLIENT: {(req.scope.get('client') or ('-', ''))[0]}, "
            f"SCHEME: {req.scope['scheme']}, "
            f"METHOD: {req.method}, "
            f"PATH: {req.path}, "
            f"STATUS_CODE: {status_code}"
        )

    def register_static_controller(self, base_path: str):
        static_controller_dec = path(f"{base_path}", open_api_spec=False)
        static_controller = static_controller_dec(Static)
        self.register_controller(static_controller, with_url_prefix=False)  # type: ignore

    def register_static_pages_controller(self, base_path: str):
        if not self.configs.USE_STATIC_PAGES:
            return

        static_pages_controller_dec = path(f"{base_path}", open_api_spec=False)
        static_pages_controller = static_pages_controller_dec(StaticPages)
        self.register_controller(static_pages_controller)
        self._url_for_alias[self.configs.STATIC_PAGES_CONTROLLER_NAME] = (
            "StaticPages.get"
        )

    def register_openapi_controller(self):
        if not self.configs.OPEN_API:
            return

        # The specification itself is built lazily on first access, so that
        # controllers registered later (e.g. by extensions) are included.
        openapi_controller_dec = path(self.configs.OPEN_API_URL, open_api_spec=False)
        openapi_controller = openapi_controller_dec(OpenAPIController)
        self.register_controller(openapi_controller)

    def register_middleware(
        self,
        middleware_class: Type[MiddlewareBase],
        *,
        order: int | None = None,
    ) -> None:
        """
        Registers a middleware class with the application.

        Middleware instances are not created immediately. They are instantiated
        only when the HTTP application is built.

        This allows extensions to register middleware during app initialization
        without forcing the HTTP app to build in CLI mode.
        """
        if self._is_built:
            raise RuntimeError(
                f"Cannot register middleware {middleware_class.__name__!r} "
                "after the application has already been built."
            )

        if middleware_class in self._middleware_classes.values():
            return

        if not getattr(middleware_class, "_middleware", False):
            return

        if getattr(middleware_class, "_ignore", False):
            return

        decorator_order = cast(int | None, getattr(middleware_class, "_order", None))
        default_order = cast(int | None, getattr(middleware_class, "_order_", None))
        here_set_order = order

        if default_order is not None and (
            decorator_order is not None or here_set_order is not None
        ):
            self.logger.warning(f"""Middleware {middleware_class.__name__} has default order {default_order}
                            but has set order {decorator_order or here_set_order}. This can lead to unexpected problems.
                            It is suggested that the order on middleware with default order number is not reset.""")

        # "is not None", not "or": an explicit order of 0 is a valid position.
        original_order = next(
            (
                value
                for value in (here_set_order, decorator_order, default_order)
                if value is not None
            ),
            None,
        )
        if original_order is None:
            raise ValueError(
                f"Middleware {middleware_class.__name__} has no set order."
            )

        resolved_order = original_order

        while resolved_order in self._middleware_classes:
            resolved_order += 1

        if resolved_order != original_order:
            self.logger.warning(
                f"For middleware {middleware_class.__name__}: "
                f"Order {original_order} is already taken, "
                f"assigned order {resolved_order} instead."
            )

        self.logger.info(
            f"Registering middleware: {middleware_class.__name__} "
            f"(order={resolved_order})"
        )

        self._middleware_classes[resolved_order] = middleware_class

    def build(self) -> None:
        """
        Build the final app by wrapping self._app in all middleware.

        Lower middleware order values are processed first and become outer
        middleware.
        """
        if self.configs.STARTUP_BANNER:
            print(PATERA_ASCIIART)

        built_app: AppCallableType = self._base_app

        for order_key in sorted(self._middleware_classes.keys(), reverse=True):
            middleware_class = self._middleware_classes[order_key]
            built_app = cast(
                AppCallableType,
                middleware_class(self, built_app),
            )
            if isinstance(built_app, CORSMiddleware):
                self._cors_middleware = built_app

        self._app = built_app
        self._is_built = True

        mode = "development" if self.configs.DEBUG else "production"
        self.logger.info(
            f"{self.app_name} started in {mode} mode at "
            f"{self.configs.PROTOCOL}://{self.configs.HOST}:{self.configs.PORT}"
            f"{self.url_prefix}"
        )
        if self.configs.STARTUP_BANNER:
            print_startup_message(
                host=self.configs.HOST,
                port=self.configs.PORT,
                debug_mode=self.configs.DEBUG,
                app_name=self.app_name,
                scheme=self.configs.PROTOCOL,
                url_prefix=self.url_prefix,
            )

    def add_extension(self, extension: Injectable):
        """
        Adds extension to extension map.
        """
        name = pascal_to_upper_snake(extension.__class__.__name__)

        if self._extensions.get(name, None) is not None:
            return

        self._extensions[name] = extension

    def get_extension(self, extension_type: Type[ExtT]) -> ExtT:
        """
        Returns a registered extension by class.

        Example:
            db_manager = app.get_extension(SqlDatabaseManager)
        """
        name = pascal_to_upper_snake(extension_type.__name__)
        extension = self._extensions.get(name)

        if extension is None:
            raise KeyError(f"Extension {extension_type.__name__!r} is not registered.")

        if not isinstance(extension, extension_type):
            raise TypeError(
                f"Registered extension {name!r} is not an instance of "
                f"{extension_type.__name__}."
            )

        return cast(ExtT, extension)

    def _add_route_function(
        self,
        method: str,
        url_path: str,
        func: Callable,
        endpoint_name: str,
    ):
        """
        Adds the function to the Router.
        Raises DuplicateRouteError if a different handler already serves the
        same method and path.
        """
        if method == HttpMethod.SOCKET.value:
            self._socket_router.add_route(url_path, func, [method], endpoint_name)
        else:
            self.router.add_route(url_path, func, [method], endpoint_name)

    def register_controller(
        self,
        *ctrls: "type[Controller]",
        with_url_prefix: bool = True,
    ):
        """
        Registers controller classes with the application. Their routes get
        the URL_PREFIX setting in front unless with_url_prefix is False.
        """
        base_path: str = self.url_prefix if with_url_prefix else ""

        for ctrl in ctrls:
            dev_only: bool = getattr(ctrl, "_development", False)
            ignore: bool = getattr(ctrl, "_ignore", False)

            if ignore or (dev_only and not self.configs.DEBUG):
                continue

            ctrl_path: str | None = cast(
                str | None, getattr(ctrl, "_controller_path", None)
            )
            ctrl_open_api_spec = getattr(ctrl, "_include_open_api_spec")
            ctrl_open_api_tags = getattr(ctrl, "_open_api_tags", None)
            ctrl_alias = getattr(ctrl, "_alias", None)

            if ctrl_path is None:
                continue

            # Controllers are keyed by class name (the same name used for
            # endpoint names), so several controllers may share a base path.
            registered = self._controllers.get(ctrl.__name__)
            if registered is not None:
                if registered.__class__ is ctrl:
                    continue
                raise ValueError(
                    f"Two controllers are named {ctrl.__name__!r} "
                    f"({registered.__class__.__module__} and {ctrl.__module__}). "
                    "Endpoint names (url_for) are built from the class name, so "
                    "rename one of them."
                )

            ctrl_instance = ctrl(
                self,
                ctrl_path,
                ctrl_open_api_spec,
                ctrl_open_api_tags,
                ctrl_alias,
            )
            self.logger.info(f"Registering controller: {ctrl.__name__}")
            self._controllers[ctrl.__name__] = ctrl_instance
            # Invalidate a previously built OpenAPI specification.
            self._json_spec = None

            endpoint_methods: dict[str, dict[str, str | Callable]] = (
                ctrl_instance.get_endpoint_methods()
            )

            for url_path, method in endpoint_methods.get(
                HttpMethod.SOCKET.value, {}
            ).items():
                self._check_socket_handler(
                    ctrl, cast(Callable, cast(dict, method)["method"])
                )

            for http_method, endpoints in endpoint_methods.items():
                for url_path, method in endpoints.items():
                    method_name: Callable = method["method"].__name__  # type: ignore

                    endpoint_name: str = (
                        f"{ctrl_instance.__class__.__name__}.{method_name}"
                    )

                    names: list[str] = [endpoint_name]

                    if ctrl_alias:
                        alias_name = f"{ctrl_alias}.{method_name}"
                        names.append(alias_name)

                    # "/" + "/hello" is "/hello", not "//hello".
                    rule = re.sub(
                        r"/{2,}", "/", base_path + ctrl_instance.path + url_path
                    )
                    for name in names:
                        self._add_route_function(
                            http_method,
                            rule,
                            cast(Callable, cast(dict, method)["method"]),
                            name,
                        )

    # Decorators that work through HTTP middleware (authentication and
    # database transactions), which does not run for WebSocket handlers.
    _MIDDLEWARE_DECORATORS: dict[str, str] = {
        "_authentication": "@login_required / @role_required",
        "_transactional": "@transactional",
    }

    def _check_socket_handler(self, ctrl: type, handler: Callable) -> None:
        """
        Refuses a WebSocket handler that carries a decorator that only works
        through HTTP middleware: it would be silently ignored, and a socket
        meant to require a login would be open to everyone.
        """
        for attribute, decorator in self._MIDDLEWARE_DECORATORS.items():
            if getattr(handler, attribute, None) or getattr(ctrl, attribute, None):
                raise ValueError(
                    f"{ctrl.__name__}.{handler.__name__} is a WebSocket handler "
                    f"with {decorator} (on the handler or its controller). HTTP "
                    "middleware does not run for WebSockets, so it would have no "
                    "effect. Check the user or open a session inside the handler, "
                    "and keep sockets in a controller of their own."
                )

    def get_controller(self, ctrl: "type[Controller] | str") -> Optional[Controller]:
        """
        Returns the registered controller instance for a controller class
        (or class name), or None if it is not registered.
        """
        name = ctrl if isinstance(ctrl, str) else ctrl.__name__
        return self._controllers.get(name)

    @property
    def controllers(self) -> "dict[str, Controller]":
        """Registered controller instances by controller class name."""
        return self._controllers

    def register_cli_controller(self, ctrl: CLIController) -> None:
        if not self._cli_mode:
            return
        if not getattr(ctrl, "_cli_controller", False):
            return
        if getattr(ctrl, "_ignore", False):
            return
        registered = self._cli_controllers.get(ctrl.ctrl_name)
        if registered is not None and registered is not ctrl:
            raise ValueError(
                f"CLI controller name {ctrl.ctrl_name!r} is used by both "
                f"{registered.__class__.__name__} and {ctrl.__class__.__name__}. "
                "Give one of them a different name."
            )
        self.logger.info(
            f"Registering CLI controller: {ctrl.ctrl_name} ({ctrl.__class__.__name__})"
        )
        self._cli_controllers[ctrl.ctrl_name] = ctrl

    def register_exception_handler(self, *handlers: "type[ExceptionHandler]"):
        """
        Registers exception handler classes with the application.

        A handler class that is already registered is skipped. A different
        class with the same name raises ValueError.
        """

        for handler in handlers:
            registered = self._exception_handler_instances.get(handler.__name__)
            if registered is not None:
                if registered.__class__ is not handler:
                    raise ValueError(
                        f"Another exception handler named {handler.__name__!r} "
                        "is already registered."
                    )
                continue
            if not getattr(handler, "_exc_handler", False):
                continue
            if getattr(handler, "_ignore", False):
                continue
            self.logger.info(f"Registering exception handler: {handler.__name__}")
            handler_instance = handler(self)

            self._exception_handler_instances[handler_instance.__class__.__name__] = (
                handler_instance
            )

            handled_exceptions = handler_instance.get_exception_mapping()
            self._exception_handlers.update(handled_exceptions)

    def url_for(self, endpoint: str, **values) -> str:
        """
        Returns URL for endpoint method.
        """
        endpoint = self._url_for_alias.get(endpoint, endpoint)
        adapter = self.router.url_map.bind("")

        try:
            return adapter.build(endpoint, values)
        except NotFound as exc:
            raise ValueError(f"Endpoint '{endpoint}' does not exist.") from exc
        except MethodNotAllowed as exc:
            raise ValueError(
                f"Endpoint '{endpoint}' exists but does not allow the method."
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Error building URL for endpoint '{endpoint}': {exc}"
            ) from exc

    def build_openapi_spec(self):
        """Builds open api spec."""
        from .open_api import build_openapi

        self._json_spec = build_openapi(
            self._controllers,
            title=self.app_name,
            version=self.version,
            openapi_version=OPEN_API_VERSION,
            # Relative to wherever the document is served, so "Try it out"
            # calls the same origin in development, production and behind a
            # proxy (an absolute HOST:PORT would point at the bind address).
            servers=[self.url_prefix or "/"],
            description=self._configs.OPEN_API_DESCRIPTION,
        )
        return self._json_spec

    def add_on_startup_method(self, func: Callable):
        """
        Adds method to on_startup collection.
        """
        self._on_startup_methods.append(func)

    def add_on_shutdown_method(self, func: Callable):
        """
        Adds method to on_shutdown collection.
        """
        self._on_shutdown_methods.append(func)

    def register_alias(self, alias: str, endpoint: str):
        """
        Registers an alias for an endpoint name.
        Useful for url_for lookups.
        """
        self._url_for_alias[alias] = endpoint

    def cli_commands(self) -> "list[CLICommand]":
        """Lists every registered CLI command, sorted by name."""
        commands = [
            command
            for ctrl in self._cli_controllers.values()
            for command in ctrl.commands()
        ]
        return sorted(commands, key=lambda command: command.name)

    def print_cli_commands(self, file: Any = None) -> None:
        """Prints the registered CLI commands with their arguments and help."""
        commands = self.cli_commands()
        if not commands:
            print("No CLI commands are registered.", file=file)
            return
        rows = [(f"{c.name} {c.usage}".strip(), c.help) for c in commands]
        width = max(len(left) for left, _ in rows)
        print("Available commands:", file=file)
        for left, help_text in rows:
            print(f"  {left.ljust(width)}  {help_text}".rstrip(), file=file)

    def run_cli(self, command_name: str, *args, **kwargs) -> None:
        """
        Runs the command ``command_name``, written as
        ``<controller>:<command>``. An invalid name, an unknown controller
        or an unknown command prints an error to standard error and exits
        with status 1.
        """
        from .cli.start_project import cli_fail

        if command_name is None or ":" not in command_name:
            cli_fail(
                "Invalid command name. Command name must be of the format "
                "CLIController:Command"
            )

        ctrl_name, command = command_name.split(":", 1)
        ctrl = cast(CLIController, self._cli_controllers.get(ctrl_name, None))

        if ctrl is None:
            cli_fail(f"ERROR: CLI controller with name {ctrl_name} was not found")

        method = ctrl.find_method(command)

        if method is None:
            cli_fail(
                f"CLI method with name {command} in controller {ctrl_name} not found."
            )

        ctrl.run_command(method, *args, **kwargs)

    def add_template_path(self, path: str):
        """Adds a template path (searched after the already registered ones)."""
        if path in self._all_templates_paths:
            return
        self._all_templates_paths.append(path)
        self.logger.info(f"Registered templates path: {path}")

    def add_template_prefix(self, prefix: str, path: str) -> None:
        """
        Makes the templates in ``path`` available as "<prefix>/<template>".
        Prefixed templates never collide with the regular template paths.
        """
        self._template_prefix_loaders[prefix] = FileSystemLoader(path)

    def _register_app_extensions(self) -> None:
        """Registers application extensions."""
        app_extensions = getattr(self.__class__, "app_extensions", [])

        for extension in app_extensions:
            if not inspect.isclass(extension):
                raise TypeError(
                    "Items in 'app_extensions' must be extension classes, "
                    "not instances."
                )

            if not issubclass(extension, BaseExtension):
                raise TypeError(
                    f"App extension {extension.__name__} must inherit from "
                    "BaseExtension."
                )
            if getattr(extension, "_ignore", False):
                continue
            self.app.logger.info(f"Registering app extension: {extension.__name__}")
            self._resolve_dependency(extension)

    @property
    def json_spec(self) -> dict | None:
        """OpenAPI specification of the app (built on first access)."""
        if self._json_spec is None and self.configs.OPEN_API:
            self.build_openapi_spec()
        return self._json_spec

    @property
    def router(self) -> Router:
        """Router instance property of the app."""
        return self._router

    @property
    def configs(self) -> ConfT:
        """
        Returns configuration object.
        """
        return self._configs

    @property
    def root_path(self) -> str:
        """
        Returns root path of application.
        """
        return self._root_path

    @property
    def url_prefix(self) -> str:
        """The URL_PREFIX setting: the prefix of every controller route ('' for none)."""
        return self._configs.URL_PREFIX

    @property
    def app(self):
        """
        Returns self.

        For compatibility with the Controller class, which contains the app
        object on the app property.
        """
        return self

    @property
    def static_files_path(self) -> str:
        """Static files path."""
        return self._static_files_path

    @property
    def version(self) -> str:
        return self._configs.VERSION

    @property
    def app_name(self) -> str:
        return self._configs.APP_NAME

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def jinja_environment(self) -> Environment:
        return self._jinja_environment

    @property
    def request_class(self) -> Type[Request]:
        """
        Returns the Request class used by the application.
        Can be overridden in configs.
        """
        return self.configs.REQUEST_CLASS

    @property
    def response_class(self) -> Type[Response]:
        """
        Returns the Response class used by the application.
        Can be overridden in configs.
        """
        return self.configs.RESPONSE_CLASS

    @property
    def extensions(self) -> "dict[str, Injectable]":
        """Returns dictionary with all registered extensions."""
        return self._extensions

    @property
    def current_request(self) -> CurrentContextProxy:
        return current_request

    async def __call__(self, scope, receive, send):
        """
        Once built, __call__ delegates to the fully wrapped app.
        """
        if not self._is_built:
            self.build()

        if scope["type"] == ScopeType.LIFESPAN.value:
            return await self._lifespan_app(scope, receive, send)

        if scope["type"] == ScopeType.HTTP.value:
            return await self._handle_http_request(scope, receive, send)

        if scope["type"] == ScopeType.WEBSOCKET.value:
            return await self._handle_websocket_request(scope, receive, send)

        raise ValueError(f"Unsupported scope type {scope['type']}")

    async def _handle_websocket_request(self, scope, receive, send):
        """
        Handles websocket requests.
        """
        method: str = "SOCKET"
        url_path: str = scope["path"]

        self._log_request(scope, method, url_path)

        try:
            route_handler, path_kwargs = self._socket_router.match(
                url_path,
                method,
            )

        except NotFound:
            self.logger.info(f"Websocket path {url_path} does not exist")

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket route not found",
                }
            )
            return

        except MethodNotAllowed as exc:
            matching_methods = list(exc.valid_methods or [])

            self.logger.warning(
                f"Method {method} not allowed for websocket path {url_path}. "
                f"Matching methods: {matching_methods}"
            )

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket method not allowed",
                }
            )
            return

        except WebsocketMismatch:
            self.logger.warning(
                f"Websocket request to {url_path} matched a non-websocket route"
            )

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket protocol mismatch",
                }
            )
            return

        except RequestRedirect as exc:
            self.logger.warning(
                f"Websocket path {url_path} requires redirect to {exc.new_url}"
            )

            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Websocket route requires redirect",
                }
            )
            return

        req = self.request_class(
            scope,
            receive,
            send,
            self,
            cast(dict, path_kwargs),
            cast(Callable, route_handler),
        )

        try:
            with request_context(
                app=self,
                request=req,
                controller=route_handler.__self__,  # type: ignore
            ) as ctx:
                try:
                    await run_sync_or_async(
                        route_handler,  # type: ignore
                        req,
                        **path_kwargs,
                    )
                finally:
                    await self._close_context_sessions(ctx)

        except Exception as exc:
            await send(
                {
                    "type": "websocket.close",
                    "code": 1011,
                    "reason": "Internal server error",
                }
            )

            self.logger.critical(
                f"Unhandled critical error in websocket: "
                f"({req.method}) {req.path}, "
                f"{req.route_parameters}: {exc}"
            )

            raise
