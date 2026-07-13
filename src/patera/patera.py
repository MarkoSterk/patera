"""
Patera application class
"""

# mypy: check-untyped-defs = True
import importlib
import os
import inspect
from collections.abc import AsyncIterator, Iterable
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
from werkzeug.exceptions import NotFound, MethodNotAllowed
from werkzeug.routing import WebsocketMismatch, RequestRedirect

from jinja2 import (
    Environment,
    FileSystemLoader,
    select_autoescape,
    StrictUndefined,
    Undefined,
)

from .ctx import current_request, CurrentContextProxy
from .exceptions.http_exceptions import HtmlAborterException, StaticPageNotFound
from .http_statuses import HttpStatus
from .http_methods import HttpMethod
from .request import Request
from .response import Response
from .utilities import (
    get_app_root_path,
    run_sync_or_async,
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
from .configuration_base import BaseConfig
from .middleware import MiddlewareBase, AppCallableType
from .cli import CLIController
from .logging.logger_config_base import LoggerBase
from .logging.inmemory_buffer import InMemoryLogBuffer
from .injectable import Injectable
from .serializers import SerializerRegistry
from .response_renderer import ResponseRenderer, ResponseRendererException
from .base_extension import BaseExtension

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

PATERA_VERSION: str = "0.114.x"

OPEN_API_VERSION: str = "3.0.3"


def print_startup_message(
    host: str,
    port: int,
    debug_mode: bool,
    *,
    app_name: str = "Application",
    scheme: str = "http",
    app_path: str = "",
) -> None:
    url = f"{scheme}://{host}:{port}{app_path}"

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


def app_path(url_path: Optional[str] = None) -> Callable[[Type[T]], Type[T]]:
    def decorator(cls: Type[T]) -> Type[T]:
        setattr(cls, "_base_url_path", url_path)
        return cls

    return decorator


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
            "Please make sure to use the @app_configs "
            "decorator with appropriate arguments."
        ),
    ):
        super().__init__(msg)


class MissingImportModule(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)


class WrongModuleLoadType(Exception):
    def __init__(self, msg: str):
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


def inherits_from(class_obj_or_instance, base_name: str) -> bool:
    # Checks inheritance via string comparison
    if inspect.isclass(class_obj_or_instance):
        return any(base.__name__ == base_name for base in class_obj_or_instance.__mro__)
    return any(
        base.__name__ == base_name for base in class_obj_or_instance.__class__.__mro__
    )


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
                "Missing valid configs object in @app_configs. "
                "Configuration class must inherit from patera.BaseConfig"
            )
        self._cli_mode = cli_mode
        self._this_path = os.path.dirname(__file__)
        self._app_base_url: str = getattr(self.__class__, "_base_url_path", "")
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

        sink_id = DefaultLogger(self).configure()
        self._logger_sink_ids.append(sink_id)

        self._router: Router = Router(self._configs.STRICT_SLASHES)
        self._socket_router: Router = Router(self._configs.STRICT_SLASHES)
        self._logger: Logger = cast(Logger, logger)

        self.log_buffer: InMemoryLogBuffer = InMemoryLogBuffer(
            maxlen=self._configs.IN_MEMORY_LOG_BUFFER_SIZE
        )

        self._log_buffer_sink_id = logger.add(
            self.log_buffer,
            level="TRACE",
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )
        self._logger_sink_ids.append(self._log_buffer_sink_id)

        self._app: AppCallableType = self._base_app

        # Middleware classes are registered here and instantiated only in build().
        # This keeps CLI mode lightweight while still allowing extensions to
        # register middleware during app initialization.
        self._middleware_classes: dict[int, Type[MiddlewareBase]] = {}

        self._controllers: dict[str, "Controller"] = {}
        self._cli_controllers: dict[str, "CLIController"] = {}
        self._exception_handlers: dict[str, Callable] = {}
        self._exception_handler_instances: dict[str, ExceptionHandler] = {}
        self._json_spec: Optional[dict] = None
        self._db_name_configs_map: dict[str, str] = {}

        self._extensions: dict[str, Injectable] = {}
        self.global_context_methods: list[Callable] = []

        self._on_startup_methods: list[Callable] = []
        self._on_shutdown_methods: list[Callable] = []

        self._get_startup_methods()
        self._get_shutdown_methods()

        self.register_static_pages_controller(self.configs.STATIC_PAGES_URL)
        self.register_static_controller(self.configs.STATIC_URL)

        self._load_controllers_exc_handlers_middleware(cli_mode)
        self._register_app_extensions()
        self._resolve_injections()

        self.register_openapi_controller()
        if not cli_mode:
            self._enable_cors()

        self.add_template_path(self._templates_path)

        self._jinja_environment.loader = FileSystemLoader(self._all_templates_paths)

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
                # if inspect.isabstract(obj):
                #     self.logger.debug(f"Is abstract class: {obj.__name__}")
                #     continue

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
                    self.logger.info(f"Registering logger sink: {obj.__name__}")
                    sink_id = obj(self).configure()
                    self._logger_sink_ids.append(sink_id)
                    continue

    def _resolve_dependency(self, target_type: type[Any]) -> Any:
        name: str = pascal_to_upper_snake(target_type.__name__)
        value = self.app._extensions.get(name, None)

        if value is None:
            value = target_type(self.app)
            self.app._extensions[name] = value

        return value

    def _resolve_config_var(
        self,
        config_name: str,
        declared_type: type[Any],
    ) -> Any:
        value = self.app.get_conf(config_name)

        if isinstance(value, declared_type):
            return value

        try:
            return declared_type(value)
        except Exception as exc:
            raise TypeError(
                f"Config variable {config_name!r} must be of type "
                f"{declared_type.__name__}, got {type(value).__name__}"
            ) from exc

    def _enable_cors(self) -> None:
        cors_enabled: bool = self._configs.CORS_ENABLED

        if not cors_enabled:
            return

        from .cors.cors_mw import CORSMiddleware

        self.register_middleware(CORSMiddleware)

    def _get_startup_methods(self) -> None:
        methods = []

        for name in dir(self):
            method = getattr(self, name)

            if callable(method) and getattr(method, "_on_startup_method", False):
                methods.append((name, method))

        methods.sort(key=lambda x: x[0])
        self._on_startup_methods = [m for _, m in methods]

    def _get_shutdown_methods(self) -> None:
        methods = []

        for name in dir(self):
            method = getattr(self, name)

            if callable(method) and getattr(method, "_on_shutdown_method", False):
                methods.append((name, method))

        methods.sort(key=lambda x: x[0])
        self._on_shutdown_methods = [m for _, m in methods]

    def get_conf(self, config_name: str, default: Any = None) -> Any:
        """
        Returns app configuration with provided config_name.
        Raises error if configuration is not found.
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
            config = getattr(config, name, None)

            if config is None:
                return default

        value = getattr(config, last_name, default)

        if value is None:
            return default

        return value

    async def _base_app(self, req: Request) -> Response:
        """
        The bare-bones application without any middleware.
        Calls the route handler directly.
        """
        if req.response.expected_body_type() is None:
            expected = _extract_response_type(req.route_handler)
            req.response._set_expected_body_type(expected)

        res: Response = await req.route_handler.__self__(req.route_handler, req)  # type: ignore

        return res

    async def abort_route_not_found(self, send):
        """
        Aborts request because route was not found.
        """
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            }
        )

        await send(
            {
                "type": "http.response.body",
                "body": b'{ "status": "error", "message": "Endpoint not found" }',
            }
        )

    async def abort_method_not_allowed(
        self,
        send,
        allowed_methods: list[str],
    ):
        """
        Aborts request because method is not allowed.
        """
        await send(
            {"type": "http.response.start", "status": HttpStatus.METHOD_NOT_ALLOWED}
        )

        await send(
            {
                "type": "http.response.body",
                "body": b"Method Not Allowed. Allowed methods: "
                + ", ".join(allowed_methods).encode(),
            }
        )

    async def abort_bad_request(self, send) -> None:
        """
        Send a 400 Bad Request response.
        """
        body = b"Bad Request"
        await send(
            {
                "type": "http.response.start",
                "status": HttpStatus.BAD_REQUEST,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )

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

        if res.zero_copy is not None:
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

            params = res.zero_copy
            file_path = params["file_path"]
            start = params["start"]
            length = params["length"]

            chunk_size = 1 * 1024 * 1024
            remaining = length

            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)

                while remaining > 0:
                    to_read = min(remaining, chunk_size)
                    chunk = await f.read(to_read)

                    if not chunk:
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

            if stream_iter is None:
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
                "body": body_bytes or b"",
                "more_body": False,
            }
        )

    async def _lifespan_app(self, _, receive, send):
        """This loop will listen for startup and shutdown."""
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                for method in self._on_startup_methods:
                    await run_sync_or_async(method)

                await send({"type": "lifespan.startup.complete"})

            elif message["type"] == "lifespan.shutdown":
                for method in self._on_shutdown_methods:
                    await run_sync_or_async(method)

                for logger_sink_id in self._logger_sink_ids:
                    self.logger.remove(logger_sink_id)

                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _handle_http_request(self, scope, receive, send):
        """
        Handles HTTP requests.
        """
        method: str = scope["method"].upper()
        url_path: str = scope["path"]

        self._log_request(scope, method, url_path)

        route_handler, path_kwargs = None, {}

        try:
            route_handler, path_kwargs = self.router.match(
                url_path,
                method,
            )
        except NotFound:
            self.logger.info(f"Path {url_path} does not exist")
            return await self.abort_route_not_found(send)
        except MethodNotAllowed as exc:
            matching_methods = list(exc.valid_methods or [])
            self.logger.warning(
                f"Method {method} not allowed for path {url_path}. "
                f"Matching methods: {matching_methods}"
            )
            return await self.abort_method_not_allowed(
                send,
                matching_methods,
            )
        except WebsocketMismatch:
            self.logger.warning(
                f"Protocol mismatch for path {url_path}: "
                f"HTTP request matched a WebSocket route"
            )
            return await self.abort_bad_request(send)

        except RequestRedirect as exc:
            self.logger.debug(f"Redirecting path {url_path} to {exc.new_url}")
            return await self.redirect_request(
                send,
                exc.new_url,
                exc.code,  # type: ignore
            )

        req = self.request_class(
            scope,
            receive,
            send,
            self,
            path_kwargs,
            cast(Callable, route_handler),
        )

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
                        return await self.send_response(res, send)

                    res: Response = await self._app(req)

                    if not isinstance(res, Response):
                        raise Exception(
                            "Return object of request handlers must be an instance "
                            "of Response"
                        )

                    response_type: Optional[Type[Any]] = (
                        req.response.expected_body_type()
                    )

                    return await self.send_response(res, send, response_type)

                except ResponseRendererException:
                    req.res.reset()
                    raise

                except HtmlAborterException as exc:
                    req.res.reset()
                    res = (await req.res.html(exc.template, context=exc.data)).status(
                        exc.status_code
                    )
                    return await self.send_response(res, send, None)
                except StaticPageNotFound:
                    # If static pages is enabled the handler may receive a request for a resource which does not exist
                    # In this case, the handler raises StaticPageNotFound which is handled here as a normal
                    # 404 - Not Found response
                    req.res.reset()
                    return await self.abort_route_not_found(send)
                except Exception as exc:
                    req.res.reset()

                    handler = (
                        self._exception_handlers.get(exc.__class__.__name__, None)
                        or None
                    )

                    if not handler:
                        handler = self._exception_handlers.get(Exception.__name__, None)

                    if not handler:
                        raise Exception from exc

                    res = await run_sync_or_async(handler, req, exc)
                    response_type = res.expected_body_type() or exc.__class__

                    return await self.send_response(res, send, response_type)

        except Exception as exc:
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

                return await self.send_response(res, send, exc.__class__)

            raise Exception from exc

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
            f"QUERY_STRING: {scope['query_string'].decode('utf-8')}"
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
        self.register_controller(static_controller, with_base_path=False)  # type: ignore

    def register_static_pages_controller(self, base_path: str):
        if not self.configs.USE_STATIC_PAGES:
            return

        static_pages_controller_dec = path(f"{base_path}", open_api_spec=False)
        static_pages_controller = static_pages_controller_dec(StaticPages)
        self.register_controller(static_pages_controller)

    def register_openapi_controller(self):
        if not self.configs.OPEN_API:
            return

        self.build_openapi_spec()

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

        original_order = here_set_order or decorator_order or default_order
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
        print(PATERA_ASCIIART)

        built_app: AppCallableType = self._base_app

        for order_key in sorted(self._middleware_classes.keys(), reverse=True):
            middleware_class = self._middleware_classes[order_key]
            built_app = cast(
                AppCallableType,
                middleware_class(self, built_app),
            )

        self._app = built_app
        self._is_built = True

        print_startup_message(
            host=self.configs.HOST,
            port=self.configs.PORT,
            debug_mode=self.configs.DEBUG,
            app_name=self.app_name,
            app_path=self._app_base_url,
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
        Raises DuplicateRoutePath if a route with the same method/path exists.
        """
        try:
            if method == HttpMethod.SOCKET.value:
                self._socket_router.add_route(url_path, func, [method], endpoint_name)
            else:
                self.router.add_route(url_path, func, [method], endpoint_name)
        except Exception as e:
            raise e

    def register_controller(
        self,
        *ctrls: "type[Controller]",
        with_base_path: bool = True,
    ):
        """Registers controller class with application."""
        base_path: str = self._app_base_url if with_base_path else ""

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

            ctrl_instance = ctrl(
                self,
                ctrl_path,
                ctrl_open_api_spec,
                ctrl_open_api_tags,
                ctrl_alias,
            )
            if self._controllers.get(ctrl_instance.path, None) is not None:
                continue
            self.logger.info(f"Registering controller: {ctrl.__name__}")
            self._controllers[ctrl_instance.path] = ctrl_instance

            endpoint_methods: dict[str, dict[str, str | Callable]] = (
                ctrl_instance.get_endpoint_methods()
            )

            if ctrl_alias:
                self._url_for_alias[ctrl_alias] = f"{ctrl_instance.__class__.__name__}"

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

                    for name in names:
                        self._add_route_function(
                            http_method,
                            base_path + ctrl_instance.path + url_path,
                            cast(Callable, cast(dict, method)["method"]),
                            name,
                        )

    def register_cli_controller(self, ctrl: CLIController) -> None:
        if not self._cli_mode:
            return
        if not getattr(ctrl, "_cli_controller", False):
            return
        if getattr(ctrl, "_ignore", False):
            return
        self.logger.info(
            f"Registering CLI controller: {ctrl.ctrl_name} ({ctrl.__class__.__name__})"
        )
        self._cli_controllers[ctrl.ctrl_name] = ctrl

    def register_exception_handler(self, *handlers: "type[ExceptionHandler]"):
        """Registers exception controller with application."""

        for handler in handlers:
            if handler.__name__ in self._exception_handler_instances:
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
            servers=[
                f"{self._configs.PROTOCOL}://{self._configs.HOST}:{self._configs.PORT}"
            ],
        )

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

    def run_cli(self, command_name: str, *args, **kwargs) -> None:
        """
        Executes the registered CLI commands.
        """
        if command_name is None or ":" not in command_name:
            print(
                "Invalid command name. Command name must be of the format "
                "CLIController:Command"
            )
            return

        ctrl_name, command = command_name.split(":", 1)
        ctrl = cast(CLIController, self._cli_controllers.get(ctrl_name, None))

        if ctrl is None:
            print(f"ERROR: CLI controller with name {ctrl_name} was not found")
            return

        method = ctrl.find_method(command)

        if method is None:
            print(
                f"CLI method with name {command} in controller {ctrl_name} not found."
            )
            return

        ctrl.run_command(method, *args, **kwargs)
        return

    def add_template_path(self, path: str):
        """Adds a template path."""
        self._all_templates_paths.append(path)
        self.logger.info(f"Registered templates path: {path}")

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

        req = Request(
            scope,
            receive,
            send,
            self,
            path_kwargs,
            cast(Callable, route_handler),
        )

        try:
            with request_context(
                app=self,
                request=req,
                controller=route_handler.__self__,  # type: ignore
            ):
                await run_sync_or_async(
                    route_handler,  # type: ignore
                    req,
                    **path_kwargs,
                )

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
