"""
Patera application class
"""

# mypy: check-untyped-defs = True
import importlib
import importlib.metadata
import os
import inspect
import sys
from collections.abc import AsyncIterator, Iterable
from enum import StrEnum
from pathlib import Path
from typing import (
    ClassVar,
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
from loguru import logger
from loguru._logger import Logger
from pydantic import BaseModel
from werkzeug.exceptions import NotFound, MethodNotAllowed

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

from .ctx import (
    current_request,
    CurrentContextProxy,
    flashed_messages,
    get_request_context,
)

# Loaded before .request: importing .request first runs into a circular
# import (request -> exceptions -> controller -> request).
from .exceptions import http_exceptions as _http_exceptions  # noqa: F401
from .request import Request
from .response import Response
from .utilities import (
    get_app_root_path,
)
from .router import Router
from .logger import DefaultLogger
from .controller import Controller
from .exceptions import ExceptionHandler
from .configuration_base import BaseConfig
from .middleware import MiddlewareBase, AppCallableType
from .cors.cors_mw import CORSMiddleware
from .cli import CLIController
from .cli.cli_controller import CLICommand
from .logging.logger_config_base import LoggerBase
from .logging.log_files import JsonLogFiles, LogFilesConfig
from .injectable import Injectable
from .serializers import SerializerRegistry
from .response_renderer import ResponseRenderer
from .base_extension import BaseExtension
from .request_record import RequestObserver, RequestRecord
from ._app.cli_commands import CliCommands
from ._app.discovery import ModuleLoader
from ._app.errors import ExceptionResolver
from ._app.http import HttpDispatcher
from ._app.lifespan import Lifespan
from ._app.middleware_stack import MiddlewareStack
from ._app.registration import Registrar
from ._app.sending import ResponseSender
from ._app.websocket import WebSocketDispatcher

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


def startup_banner(
    host: str,
    port: int,
    debug_mode: bool,
    *,
    app_name: str = "Application",
    scheme: str = "http",
    url_prefix: str = "",
) -> str:
    """The Patera ASCII art and the address box, as one block of text."""
    url = f"{scheme}://{host}:{port}{url_prefix}"
    mode_label = "DEVELOPMENT" if debug_mode else "PRODUCTION"
    lines = [
        PATERA_ASCIIART.rstrip("\n"),
        "",
        "═" * 64,
        f"  {app_name} is running",
        "─" * 64,
        f"  Mode:    {mode_label}",
        f"  Host:    {host}",
        f"  Port:    {port}",
        f"  URL:     \033]8;;{url}\033\\{url}\033]8;;\033\\",
        "═" * 64,
    ]
    return "\n".join(lines) + "\n\n"


def print_startup_message(
    host: str,
    port: int,
    debug_mode: bool,
    *,
    app_name: str = "Application",
    scheme: str = "http",
    url_prefix: str = "",
) -> None:
    """
    Writes the startup banner to stdout in one piece.

    Log sinks added with ``enqueue=True`` are written by a background
    thread, so a message logged just before the banner could otherwise
    appear in the middle of it. The queue is drained first, and the banner
    is written with a single call and flushed.
    """
    logger.complete()
    sys.stderr.flush()
    sys.stdout.write(
        startup_banner(
            host,
            port,
            debug_mode,
            app_name=app_name,
            scheme=scheme,
            url_prefix=url_prefix,
        )
    )
    sys.stdout.flush()


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

    app_extensions: ClassVar[list[Type[BaseExtension[Any, Any]]]] = []

    def __init__(self, cli_mode: bool = False):
        """Init function"""
        # Core application components for Patera
        self._core_registrar = Registrar(self)
        self._core_loader = ModuleLoader(self)
        self._core_middleware = MiddlewareStack(self)
        self._core_lifespan = Lifespan(self)
        self._core_http = HttpDispatcher(self)
        self._core_sender = ResponseSender(self)
        self._core_errors = ExceptionResolver(self)
        self._core_websocket = WebSocketDispatcher(self)
        self._core_cli = CliCommands(self)

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
        self._loggers: list[LoggerBase] = []
        self._registered_loggers: set[type] = set()

        self._jinja_environment: Environment = Environment(
            loader=None,
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined if self._configs.TEMPLATES_STRICT else Undefined,
            auto_reload=self._configs.AUTO_RELOAD,
            enable_async=True,
        )
        self._jinja_environment.globals["flashed_messages"] = flashed_messages

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
        """See ModuleLoader.load_controllers_exc_handlers_middleware."""
        return self._core_loader.load_controllers_exc_handlers_middleware(cli_mode)

    def _unique_list(self, values: list[str]) -> list[str]:
        """See ModuleLoader.unique_list."""
        return self._core_loader.unique_list(values)

    def _load_detected_modules_once(
        self,
        folders: list[str],
        name_patterns: list[str],
        load_class: Type,
    ) -> None:
        """See ModuleLoader.load_detected_modules_once."""
        return self._core_loader.load_detected_modules_once(
            folders, name_patterns, load_class
        )

    def _load_detected_module(self, file_paths: List[Path], load_class: Type) -> None:
        """See ModuleLoader.load_detected_module."""
        return self._core_loader.load_detected_module(file_paths, load_class)

    def _enable_cors(self) -> None:
        """See MiddlewareStack.enable_cors."""
        return self._core_middleware.enable_cors()

    def _marked_methods(self, marker: str) -> list[Callable]:
        """See Lifespan.marked_methods."""
        return self._core_lifespan.marked_methods(marker)

    def _get_startup_methods(self) -> None:
        """See Lifespan.get_startup_methods."""
        return self._core_lifespan.get_startup_methods()

    def _get_shutdown_methods(self) -> None:
        """See Lifespan.get_shutdown_methods."""
        return self._core_lifespan.get_shutdown_methods()

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
        """See HttpDispatcher.base_app."""
        return await self._core_http.base_app(req)

    async def _send_error(
        self,
        send,
        status_code: int,
        message: str,
        data: Any = None,
        headers: Optional[list[tuple[bytes, bytes]]] = None,
    ) -> None:
        """See HttpDispatcher.send_error."""
        return await self._core_http.send_error(
            send, status_code, message, data, headers
        )

    async def abort_route_not_found(self, send):
        """
        Aborts request because route was not found.
        """
        return await self._core_http.abort_route_not_found(send)

    async def abort_method_not_allowed(
        self,
        send,
        allowed_methods: list[str],
    ):
        """
        Aborts request because method is not allowed.
        """
        return await self._core_http.abort_method_not_allowed(send, allowed_methods)

    async def abort_bad_request(self, send) -> None:
        """
        Send a 400 Bad Request response.
        """
        return await self._core_http.abort_bad_request(send)

    async def redirect_request(
        self,
        send,
        location: str,
        status_code: int,
    ) -> None:
        """
        Send an HTTP redirect response.
        """
        return await self._core_http.redirect_request(send, location, status_code)

    def _iterate_stream(
        self,
        iterable: Union[AsyncIterable[bytes], Iterable[bytes]],
    ) -> AsyncIterator[bytes]:
        """See ResponseSender.iterate_stream."""
        return self._core_sender.iterate_stream(iterable)

    def _normalize_chunk(self, chunk: Any) -> bytes:
        """See ResponseSender.normalize_chunk."""
        return self._core_sender.normalize_chunk(chunk)

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
        return await self._core_sender.send_response(res, send, response_type)

    async def _lifespan_app(self, _, receive, send):
        """See Lifespan.lifespan_app."""
        return await self._core_lifespan.lifespan_app(_, receive, send)

    async def _finish_background_tasks(self) -> None:
        """See Lifespan.finish_background_tasks."""
        return await self._core_lifespan.finish_background_tasks()

    def _attach_logger_sinks(self) -> None:
        """See Lifespan.attach_logger_sinks."""
        return self._core_lifespan.attach_logger_sinks()

    def _remove_logger_sinks(self) -> None:
        """See Lifespan.remove_logger_sinks."""
        return self._core_lifespan.remove_logger_sinks()

    def add_request_observer(self, observer: RequestObserver) -> None:
        """
        Calls ``observer(record)`` with a ``RequestRecord`` after every HTTP
        request, including those answered by the router (404, 405), static
        resources and failed requests. Observers run in the request's task
        once its response has been sent, so they must be quick and must not
        block; an observer that raises is logged and skipped.
        """
        return self._core_http.add_request_observer(observer)

    async def _handle_http_request(self, scope, receive, send):
        """See HttpDispatcher.handle_http_request."""
        return await self._core_http.handle_http_request(scope, receive, send)

    def _notify_request_observers(self, record: RequestRecord) -> None:
        """See HttpDispatcher.notify_request_observers."""
        return self._core_http.notify_request_observers(record)

    async def _dispatch_http_request(self, scope, receive, send):
        """See HttpDispatcher.dispatch_http_request."""
        return await self._core_http.dispatch_http_request(scope, receive, send)

    async def _send_exception_response(self, req: Request, exc: Exception) -> None:
        """See ExceptionResolver.send_exception_response."""
        return await self._core_errors.send_exception_response(req, exc)

    async def _close_context_sessions(self, ctx: Any) -> None:
        """See WebSocketDispatcher.close_context_sessions."""
        return await self._core_websocket.close_context_sessions(ctx)

    def _match_automatic_options(
        self,
        scope: dict,
        url_path: str,
        allowed_methods: list[str],
    ) -> tuple[Callable, Any, list[str]]:
        """See HttpDispatcher.match_automatic_options."""
        return self._core_http.match_automatic_options(scope, url_path, allowed_methods)

    def _find_exception_handler(
        self,
        exc: BaseException,
        stop_at: Optional[type[BaseException]] = None,
    ) -> Optional[Callable]:
        """See ExceptionResolver.find_exception_handler."""
        return self._core_errors.find_exception_handler(exc, stop_at)

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
        return self._core_errors.default_exception_response(req, exc)

    def _log_request(self, scope, method: str, url_path: str) -> None:
        """See HttpDispatcher.log_request."""
        return self._core_http.log_request(scope, method, url_path)

    def _log_response(self, req: Request, status_code: int) -> None:
        """See HttpDispatcher.log_response."""
        return self._core_http.log_response(req, status_code)

    def register_static_controller(self, base_path: str):
        """See Registrar.register_static_controller."""
        return self._core_registrar.register_static_controller(base_path)

    def register_static_pages_controller(self, base_path: str):
        """See Registrar.register_static_pages_controller."""
        return self._core_registrar.register_static_pages_controller(base_path)

    def register_openapi_controller(self):
        """See Registrar.register_openapi_controller."""
        return self._core_registrar.register_openapi_controller()

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
        return self._core_middleware.register_middleware(middleware_class, order=order)

    def build(self) -> None:
        """
        Build the final app by wrapping self._app in all middleware.

        Lower middleware order values are processed first and become outer
        middleware.
        """
        self._core_middleware.build_chain()
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
        return self._core_registrar.add_extension(extension)

    def get_extension(self, extension_type: Type[ExtT]) -> ExtT:
        """
        Returns a registered extension by class.

        Example:
            db_manager = app.get_extension(SqlDatabaseManager)
        """
        return self._core_registrar.get_extension(extension_type)

    def _add_route_function(
        self,
        method: str,
        url_path: str,
        func: Callable,
        endpoint_name: str,
    ):
        """See Registrar.add_route_function."""
        return self._core_registrar.add_route_function(
            method, url_path, func, endpoint_name
        )

    def register_controller(
        self,
        *ctrls: "type[Controller]",
        with_url_prefix: bool = True,
    ):
        """
        Registers controller classes with the application. Their routes get
        the URL_PREFIX setting in front unless with_url_prefix is False.
        """
        return self._core_registrar.register_controller(
            *ctrls, with_url_prefix=with_url_prefix
        )

    _MIDDLEWARE_DECORATORS: ClassVar[dict[str, str]] = {
        "_authentication": "@login_required / @role_required",
        "_transactional": "@transactional",
    }

    def _check_socket_handler(self, ctrl: type, handler: Callable) -> None:
        """See WebSocketDispatcher.check_socket_handler."""
        return self._core_websocket.check_socket_handler(ctrl, handler)

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
        """See Registrar.register_cli_controller."""
        return self._core_registrar.register_cli_controller(ctrl)

    def register_exception_handler(self, *handlers: "type[ExceptionHandler]"):
        """
        Registers exception handler classes with the application.

        A handler class that is already registered is skipped. A different
        class with the same name raises ValueError.
        """
        return self._core_registrar.register_exception_handler(*handlers)

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

        # pylint: disable-next=C0415
        from .controller.params import handler_params

        self._json_spec = build_openapi(
            self._controllers,
            middleware_plans=[
                handler_params(middleware_class.middleware)
                for middleware_class in self._middleware_classes.values()
                if getattr(middleware_class, "open_api_spec", True)
            ],
            title=self.app_name,
            version=self.version,
            openapi_version=OPEN_API_VERSION,
            servers=[self.url_prefix or "/"],
            description=self._configs.OPEN_API_DESCRIPTION,
        )
        return self._json_spec

    def add_on_startup_method(self, func: Callable):
        """
        Adds method to on_startup collection.
        """
        return self._core_registrar.add_on_startup_method(func)

    def add_on_shutdown_method(self, func: Callable):
        """
        Adds method to on_shutdown collection.
        """
        return self._core_registrar.add_on_shutdown_method(func)

    def register_alias(self, alias: str, endpoint: str):
        """
        Registers an alias for an endpoint name.
        Useful for url_for lookups.
        """
        return self._core_registrar.register_alias(alias, endpoint)

    def cli_commands(self) -> "list[CLICommand]":
        """Lists every registered CLI command, sorted by name."""
        return self._core_cli.cli_commands()

    def print_cli_commands(self, file: Any = None) -> None:
        """Prints the registered CLI commands with their arguments and help."""
        return self._core_cli.print_cli_commands(file)

    def run_cli(self, command_name: str, *args, **kwargs) -> None:
        """
        Runs the command ``command_name``, written as
        ``<controller>:<command>``. An invalid name, an unknown controller
        or an unknown command prints an error to standard error and exits
        with status 1.
        """
        return self._core_cli.run_cli(command_name, *args, **kwargs)

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
        """See Registrar.register_app_extensions."""
        return self._core_registrar.register_app_extensions()

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

    def flash_message(self, message: str, status: str | None = None) -> None:
        """Append a message for this request's templates without consuming it.

        Requires an active context. Messages do not survive redirects.
        """
        get_request_context().flashed_messages.append((message, status))

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
        """See WebSocketDispatcher.handle_websocket_request."""
        return await self._core_websocket.handle_websocket_request(scope, receive, send)
