"""
Patera application class
"""

# mypy: check-untyped-defs = True
import os
import inspect
import json
from collections.abc import AsyncIterator, Iterable
from enum import StrEnum
from typing import (
    Any,
    Callable,
    Mapping,
    Optional,
    Type,
    TypeVar,
    cast,
    AsyncIterable,
    Union,
)
import aiofiles
from loguru import logger
from werkzeug.exceptions import NotFound, MethodNotAllowed
from pydantic import BaseModel

from jinja2 import (
    Environment,
    FileSystemLoader,
    select_autoescape,
    StrictUndefined,
    Undefined,
)

from patera.media_types import MediaType

from .exceptions.http_exceptions import HtmlAborterException
from .http_statuses import HttpStatus
from .http_methods import HttpMethod
from .request import Request
from .response import Response
from .utilities import get_app_root_path, run_sync_or_async, import_module
from .router import Router
from .static import Static
from .open_api import OpenAPIController
from .controller import path
from .logger import DefaultLogger

from .controller import Controller
from .exceptions import ExceptionHandler
from .base_extension import BaseExtension
from .configuration_base import BaseConfig
from .middleware import MiddlewareBase, AppCallableType
from .cli import CLIController
from .logging.logger_config_base import LoggerBase
from .logging.inmemory_buffer import InMemoryLogBuffer

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

PATERA_VERSION: str = "0.111.x"

T = TypeVar("T", bound="Patera")


def app_path(url_path: Optional[str] = None) -> Callable[[Type[T]], Type[T]]:
    def decorator(cls: Type[T]) -> Type[T]:
        setattr(cls, "_base_url_path", url_path)
        return cls

    return decorator


def app(import_name: str, configs: Type[BaseConfig]) -> Callable[[Type[T]], Type[T]]:
    def decorator(cls: Type[T]) -> Type[T]:
        setattr(cls, "_app_configs", {"import_name": import_name, "configs": configs})
        return cls

    return decorator


def on_startup(func) -> Callable:
    """
    Decorated methods will run in alphabetical order on app startup
    """
    setattr(func, "_on_startup_method", True)
    return func


def on_shutdown(func) -> Callable:
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


def validate_config(config_obj_or_type: Type[BaseConfig] | BaseConfig) -> BaseConfig:
    # If it's already an instance
    if isinstance(config_obj_or_type, BaseConfig):
        return cast(BaseConfig, config_obj_or_type)  # already validated by Pydantic

    if inspect.isclass(config_obj_or_type) and issubclass(
        config_obj_or_type, BaseConfig
    ):
        try:
            instance = config_obj_or_type()  # type: ignore[call-arg]
        except Exception as e:
            raise MissingAppConfigurations(
                f"Could not instantiate config class {config_obj_or_type.__name__}: {e}"
            ) from e
        return BaseConfig.model_validate(instance.model_dump())

    raise MissingAppConfigurations("Configs must be a subclass of patera.BaseConfig.")


def inherits_from(class_obj_or_instance, base_name: str) -> bool:
    # Checks inheritance via string comparison
    if inspect.isclass(class_obj_or_instance):
        return any(base.__name__ == base_name for base in class_obj_or_instance.__mro__)
    return any(
        base.__name__ == base_name for base in class_obj_or_instance.__class__.__mro__
    )


class Patera:
    """Patera class implementation. Used to create a new application instance"""

    def __init__(self, cli_mode: bool = False):
        """Init function"""
        app_configs: dict[str, str | object | dict] | None = getattr(
            self.__class__, "_app_configs", None
        )
        if app_configs is None:
            raise MissingAppConfigurations()

        import_name: str = cast(str, app_configs.get("import_name", None))
        configs: Type[BaseConfig] = cast(
            Type[BaseConfig], app_configs.get("configs", None)
        )
        if configs is None or not issubclass(configs, BaseConfig):
            raise MissingAppConfigurations(
                "Missing valid configs object in @app_configs. "
                "Configuration class must inherit from patera.BaseConfig"
            )
        self._this_path = os.path.dirname(__file__)
        self._app_base_url: str = getattr(self.__class__, "_base_url_path", "")
        self._is_built = False
        self._root_path = get_app_root_path(import_name)
        # Dictionary which holds application configurations
        validated_configs: BaseConfig = validate_config(configs)
        self._configs = {**validated_configs.model_dump()}
        static_dir = self.get_conf("STATIC_DIR").lstrip("/\\")
        self._static_files_path = os.path.join(self._root_path, static_dir)
        self._templates_path = self._root_path + self.get_conf("TEMPLATES_DIR")

        self._all_templates_paths = [self._templates_path]

        self._url_for_alias: dict[str, str] = {
            self.get_conf("STATIC_CONTROLLER_NAME"): "Static.get"
        }
        self._logger_sink_ids: list[int] = []

        # creates Jinja2 environment for entire app
        self._jinja_environment = Environment(
            loader=None,
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined
            if self.get_conf("TEMPLATES_STRICT", True)
            else Undefined,
            auto_reload=self.get_conf("AUTO_RELOAD", False),
            enable_async=True,
        )
        sink_id = DefaultLogger(self).configure()
        self._logger_sink_ids.append(sink_id)

        self._router = Router(self.get_conf("STRICT_SLASHES", False))
        self._socket_router = Router(self.get_conf("STRICT_SLASHES", False))
        self._logger = logger

        self.log_buffer = InMemoryLogBuffer(
            maxlen=self._configs.get("IN_MEMORY_LOG_BUFFER_SIZE", 1)
        )
        # Capture everything (TRACE and above) in the in-memory log buffer
        self._log_buffer_sink_id = logger.add(
            self.log_buffer, level="TRACE", enqueue=True, backtrace=True, diagnose=False
        )
        self._logger_sink_ids.append(self._log_buffer_sink_id)

        self._app: AppCallableType = self._base_app
        self._middleware: list[Callable] = []
        self._controllers: dict[str, "Controller"] = {}
        self._cli_controllers: dict[str, "CLIController"] = {}
        self._exception_handlers: dict[str, Callable] = {}
        self._json_spec: Optional[dict] = None
        self._db_models: dict[str, list[Type]] = {}
        self._db_name_configs_map: dict[str, str] = {}

        self._extensions: dict = {}
        self.global_context_methods: list[Callable] = []

        self._on_startup_methods: list[Callable] = []
        self._on_shutdown_methods: list[Callable] = []

        self._get_startup_methods()
        self._get_shutdown_methods()

        models: Optional[list[str]] = self.get_conf("MODELS", None)
        controllers: Optional[list[str]] = self.get_conf("CONTROLLERS", None)
        cli_controllers: Optional[list[str]] = self.get_conf("CLI_CONTROLLERS", None)
        exception_handlers: Optional[list[str]] = self.get_conf(
            "EXCEPTION_HANDLERS", None
        )
        extensions: Optional[list[str]] = self.get_conf("EXTENSIONS", None)
        middleware: Optional[list[str]] = self.get_conf("MIDDLEWARE", None)
        loggers: Optional[list[str]] = self.get_conf("LOGGERS", None)
        # if NOT in CLI mode (cli_mode = False)
        # all extensions, models, controllers, exception handlers and middleware
        # is registered and configured with the app.
        if not cli_mode:
            self._enable_cors()  # enables CORS middleware if configured
            self._load_modules(loggers)
            self._load_modules(models)
            self._load_modules(extensions)
            self._load_modules(controllers)
            self._load_modules(cli_controllers)
            self._load_modules(exception_handlers)
            self._load_modules(middleware)
        # if in CLI mode only models and extension are registered
        # and configured with the app
        else:
            self._load_modules(models)
            self._load_modules(extensions)
            self._load_modules(cli_controllers)

        self._jinja_environment.loader = FileSystemLoader(self._all_templates_paths)

    def _enable_cors(self):
        cors_enabled: bool = self.get_conf("CORS_ENABLED", True)
        if not cors_enabled:
            return

        # pylint: disable-next=C0415
        from .cors.cors_mw import CORSMiddleware

        self.logger.info(f"Registering middleware: {CORSMiddleware.__name__}")
        self._middleware.append(
            # pylint: disable-next=W0108
            lambda app, next_app: CORSMiddleware(app, next_app)
        )

    def _load_modules(self, modules: Optional[list[str]] = None):
        if modules is None:
            return
        for import_string in modules:
            obj = import_module(import_string)
            if obj is None:
                raise MissingImportModule(
                    f"Failed to load module: {import_string}. Check path in configurations."
                )
            if inspect.isclass(obj) and issubclass(obj, Controller):
                self.logger.info(f"Registering controller: {obj.__name__}")
                self.register_controller(obj)
                continue
            if inspect.isclass(obj) and issubclass(obj, ExceptionHandler):
                self.logger.info(f"Registering exception handler: {obj.__name__}")
                self.register_exception_handler(obj)
                continue
            if inherits_from(obj, "SqlDatabase"):
                self.logger.info(
                    f"Initilizing database: {obj.__class__.__name__} ({obj.configs_name})"
                )
                obj.init_app(self)
                self._db_name_configs_map[obj.db_name] = obj.configs_name
                continue
            if inherits_from(obj, "BaseExtension"):
                ext_name = ""
                conf_name = ""
                if isinstance(obj, BaseExtension):
                    obj.init_app(self)
                    ext_name = obj.__class__.__name__
                    conf_name = obj.configs_name
                else:
                    # if passed extension is not yet initilized
                    obj_inst = obj()
                    obj_inst.init_app(self)
                    ext_name = obj_inst.__class__.__name__
                    conf_name = obj_inst.configs_name
                self.logger.info(f"Initilizing extension: {ext_name} ({conf_name})")
                continue
            if inspect.isclass(obj) and inherits_from(obj, "DeclarativeBaseModel"):
                self.logger.info(f"Loaded database model: {obj.__name__}")
                if obj.db_name() not in self._db_models:
                    self._db_models[obj.db_name()] = []
                self._db_models[obj.db_name()].append(obj)
                continue
            if inspect.isclass(obj) and issubclass(obj, CLIController):
                self.logger.info(f"Registering cli controller: {obj.__name__}")
                cli_controller = obj(self)
                self._cli_controllers[obj.__name__] = cli_controller
                continue
            if inspect.isclass(obj) and issubclass(obj, MiddlewareBase):
                self.logger.info(f"Registering middleware: {obj.__name__}")
                self._middleware.append(
                    lambda app, next_app, mdlwr_class=obj: mdlwr_class(app, next_app)
                )
                continue
            if inspect.isclass(obj) and issubclass(obj, LoggerBase):
                sink_id = obj(self).configure()
                self._logger_sink_ids.append(sink_id)
                print(f"Registering logger: {obj.__name__}")
                continue
            raise WrongModuleLoadType(
                f"Failed to load module {obj.__name__ or obj.__class__.__name__}. Extensions can be passed as instances or classes (if custom config names are not used and instance is not used elsewhere). Controllers, cli controllers, exception handlers and middleware as classes."
            )

    def _get_startup_methods(self):
        methods = []
        for name in dir(self):
            method = getattr(self, name)
            if callable(method) and getattr(method, "_on_startup_method", False):
                methods.append((name, method))
        methods.sort(key=lambda x: x[0])  # by method name
        self._on_startup_methods = [m for _, m in methods]

    def _get_shutdown_methods(self):
        methods = []
        for name in dir(self):
            method = getattr(self, name)
            if callable(method) and getattr(method, "_on_shutdown_method", False):
                methods.append((name, method))
        methods.sort(key=lambda x: x[0])  # by method name
        self._on_shutdown_methods = [m for _, m in methods]

    def get_conf(self, config_name: str, default: Any = None) -> Any:
        """
        Returns app configuration with provided config_name.
        Raises error if configuration is not found.
        """
        return self.configs.get(config_name, default)

    def add_global_context_method(self, func: Callable):
        """
        Adds global context method to global_context_methods array
        """
        self.global_context_methods.append(func)

    async def _base_app(self, req: Request) -> Response:
        """
        The bare-bones application without any middleware.
        Calls the route handler directly.
        """
        res: Response = await run_sync_or_async(
            req.route_handler, req, **req.route_parameters
        )
        return res

    async def abort_route_not_found(
        self, send, req: Request, path_data: Mapping[str, Any]
    ):
        """
        Aborts request because route was not found
        """
        exc: NotFound | MethodNotAllowed | None = path_data.get("exc")
        if exc is not None:
            handler: Callable | None = (
                self._exception_handlers.get(exc.__class__.__name__, None) or None
            )
            if handler:
                res = await run_sync_or_async(handler, req, exc)
                response_type = res.expected_body_type() or exc.__class__
                return await self.send_response(res, send, response_type)
        ##sends generic response if custom handler not available
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
        self, res: Response, send, response_type: Optional[Type[Any]] = None
    ):
        """
        Sends response
        """
        # Build headers for ASGI send
        headers = []
        for k, v in res.headers.items():
            headers.append((k.encode("utf-8"), v.encode("utf-8")))
        await send(
            {
                "type": "http.response.start",
                "status": res.status_code.value
                if isinstance(res.status_code, HttpStatus)
                else res.status_code,
                "headers": headers,
            }
        )
        # Zero-copy _parameters_ were stashed in res._zero_copy
        if res.zero_copy is not None:
            params = res.zero_copy
            file_path = params["file_path"]
            start = params["start"]
            length = params["length"]

            # stream in 1 MiB chunks
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

        if getattr(res, "is_streaming", False) and res.is_streaming:
            stream_iter = res.stream_iterable
            if stream_iter is None:
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
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

            # Final empty chunk with more_body=False
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )
            return

        if res.body and res.content_type in [
            MediaType.APPLICATION_JSON,
            MediaType.APPLICATION_PROBLEM_JSON,
            MediaType.APPLICATION_X_NDJSON,
        ]:
            if (
                response_type
                and issubclass(response_type, BaseModel)
                and isinstance(res.body, dict)
            ):
                res.body = response_type(**res.body).model_dump_json().encode("utf-8")
            elif (
                response_type
                and issubclass(response_type, BaseModel)
                and isinstance(res.body, BaseModel)
            ):
                res.body = res.body.model_dump_json().encode("utf-8")
            elif res.body and response_type is None and isinstance(res.body, BaseModel):
                res.body = res.body.model_dump_json().encode("utf-8")
            elif not response_type and isinstance(res.body, dict):
                # tries to serialize plain dict to json. Works if the dict contains only json serializable types
                res.body = json.dumps(res.body).encode("utf-8")
            elif res.body and not isinstance(res.body, (bytes, bytearray)):
                # tries to serialize other types (not bytes or bytesarray) to json
                res.body = json.dumps(res.body).encode("utf-8")

        await send(
            {
                "type": "http.response.body",
                "body": res.body or b"",
            }
        )

    async def _lifespan_app(self, _, receive, send):
        """This loop will listen for 'startup' and 'shutdown'"""
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
                return  # Exit the lifespan loop

    async def _handle_http_request(self, scope, receive, send):
        """
        Handles http requests
        """
        method: str = scope["method"].upper()
        url_path: str = scope["path"]
        self._log_request(scope, method, url_path)

        route_handler, path_kwargs = self.router.match(url_path, method)
        req = self.request_class(
            scope, receive, self, path_kwargs, cast(Callable, route_handler)
        )

        if not route_handler:
            return await self.abort_route_not_found(send, req, path_kwargs)

        try:
            try:
                res: Response = await self._app(req)
                if not isinstance(res, Response):
                    # pylint: disable-next=W0719
                    raise Exception(
                        "Return object of request handlers must be an instance of Response"
                    )
                response_type: Optional[Type[Any]] = req.response.expected_body_type()
                return await self.send_response(res, send, response_type)
            except HtmlAborterException as exc:
                res = (await req.res.html(exc.template, context=exc.data)).status(
                    exc.status_code
                )
                return await self.send_response(res, send, None)
            # pylint: disable-next=W0718
            except Exception as exc:
                handler = (
                    self._exception_handlers.get(exc.__class__.__name__, None) or None
                )
                if not handler:
                    # pylint: disable-next=W0719
                    raise
                res = await run_sync_or_async(handler, req, exc)
                response_type = res.expected_body_type() or exc.__class__
                return await self.send_response(res, send, response_type)
        # pylint: disable-next=W0718
        except Exception as exc:
            # Catches every error and returns internal server error message
            # if the app is in production (DEBUG = False)
            # else reraises the error
            if not self.get_conf("DEBUG", False):
                res = req.res.json(
                    {
                        "status": "error",
                        "message": "Internal server error",
                    }
                ).status(HttpStatus.INTERNAL_SERVER_ERROR)
                self.logger.critical(
                    f"Unhandled critical error: ({req.method}) {req.path}, {req.route_parameters}"
                )
                return await self.send_response(res, send, exc.__class__)
            raise

    def _log_request(self, scope, method: str, url_path: str) -> None:
        """
        Logs incoming request
        """
        logger.info(
            f"HTTP request. CLIENT: {(scope.get('client') or ('-', ''))[0]}, SCHEME: {scope['scheme']}, METHOD: {method}, PATH: {url_path}, QUERY_STRING: {scope['query_string'].decode('utf-8')}"
        )

    def register_static_controller(self, base_path: str):
        print("Register static: ", base_path)
        static_controller_dec = path(f"{base_path}", open_api_spec=False)
        static_controller = static_controller_dec(Static)
        self.register_controller(static_controller, with_base_path=False)  # type: ignore

    def register_openapi_controller(self):
        openapi_controller_dec = path(
            self.get_conf("OPEN_API_URL"), open_api_spec=False
        )
        openapi_controller = openapi_controller_dec(OpenAPIController)
        self.register_controller(openapi_controller)

    def build(self) -> None:
        """
        Build the final app by wrapping self._app in all middleware.
        Apply them in reverse order so the first middleware in the list
        is the outermost layer.
        """
        print(PATERA_ASCIIART)
        print(f"Starting Patera {PATERA_VERSION} application '{self.app_name}'")
        self.register_static_controller(self.get_conf("STATIC_URL"))
        if self.get_conf("OPEN_API", False):
            self.build_openapi_spec()
            self.register_openapi_controller()
        built_app: AppCallableType = self._base_app
        for factory in reversed(self._middleware):
            built_app = factory(self, built_app)
        self._app = built_app
        self._is_built = True

    def add_extension(self, extension):
        """
        Adds extension to extension map
        """
        ext_name = extension.configs_name
        self._extensions[ext_name] = extension

    def activate_extension(self, extension: "Type[BaseExtension]"):
        extension_instance = extension()
        extension_instance.init_app(self)

    def _add_route_function(
        self, method: str, url_path: str, func: Callable, endpoint_name: str
    ):
        """
        Adds the function to the Router.
        Raises DuplicateRoutePath if a route with the same (method, path) is already registered.
        """
        try:
            if method == HttpMethod.SOCKET.value:
                self._socket_router.add_route(url_path, func, [method], endpoint_name)
            else:
                self.router.add_route(url_path, func, [method], endpoint_name)
        except Exception as e:
            raise e

    def register_controller(
        self, *ctrls: "type[Controller]", with_base_path: bool = True
    ):
        """Registers controller class with application"""
        base_path: str = self._app_base_url if with_base_path else ""
        for ctrl in ctrls:
            dev_only: bool = getattr(ctrl, "_development", False)
            if dev_only and not self.get_conf("DEBUG", False):
                continue
            ctrl_path: str = getattr(ctrl, "_controller_path")
            ctrl_open_api_spec = getattr(ctrl, "_include_open_api_spec")
            ctrl_open_api_tags = getattr(ctrl, "_open_api_tags", None)
            ctrl_instance = ctrl(
                self, ctrl_path, ctrl_open_api_spec, ctrl_open_api_tags
            )

            self._controllers[ctrl_instance.path] = ctrl_instance
            endpoint_methods: dict[str, dict[str, str | Callable]] = (
                ctrl_instance.get_endpoint_methods()
            )
            for http_method, endpoints in endpoint_methods.items():
                for url_path, method in endpoints.items():
                    method_name: Callable = method["method"].__name__  # type: ignore
                    # handler: Callable = getattr(ctrl_instance, method_name) # type: ignore
                    endpoint_name: str = (
                        f"{ctrl_instance.__class__.__name__}.{method_name}"
                    )
                    self._add_route_function(
                        http_method,
                        base_path + ctrl_instance.path + url_path,
                        cast(Callable, cast(dict, method)["method"]),
                        endpoint_name,
                    )

    def register_exception_handler(self, *handlers: "type[ExceptionHandler]"):
        """Registers exception controller with application"""
        for handler in handlers:
            handler_instance = handler(self)
            handled_exceptions = handler_instance.get_exception_mapping()
            self._exception_handlers.update(handled_exceptions)

    def url_for(self, endpoint: str, **values) -> str:
        """
        Returns url for endpoint method
        :param endpoint: the name of the endpoint handler method namespaced
        with the controller name
        :param values: dynamic route parameters
        :return: url (string) for endpoint
        """
        endpoint = self._url_for_alias.get(endpoint, endpoint)
        adapter = self.router.url_map.bind("")  # Binds map to base url
        # If a value starts with a forward slash, systems like MacOS/Linux treat it as an absolute path
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
        """Builds open api spec"""
        # pylint: disable-next=C0415
        from .open_api import build_openapi

        self._json_spec = build_openapi(
            self._controllers,
            title=self.app_name,
            version=self.version,
            openapi_version="3.0.3",
            servers=[f"http://localhost:{self.get_conf('PORT', 3000)}"],
        )

    def add_on_startup_method(self, func: Callable):
        """
        Adds method to on_startup collection
        """
        self._on_startup_methods.append(func)

    def add_on_shutdown_method(self, func: Callable):
        """
        Adds method to on_shutdown collection
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
                "Invalid command name. Command name must be of the format CLIController:Command"
            )
            return
        ctrl_name, command = command_name.split(":", 1)
        ctrl = cast(CLIController, self._cli_controllers.get(ctrl_name, None))
        if ctrl is None:
            print(f"CLI controller with name {ctrl_name} was not found")

        method = ctrl.find_method(command)
        if method is None:
            print(
                f"CLI method with name {command} in controller {ctrl_name} not found."
            )
            return
        ctrl.run_command(method, *args, **kwargs)
        return

    def add_template_path(self, path: str):
        """Adds a template path"""
        self._all_templates_paths.append(path)

    @property
    def json_spec(self) -> dict | None:
        return self._json_spec

    @property
    def router(self) -> Router:
        """Router instance property of the app"""
        return self._router

    @property
    def configs(self) -> dict[str, Any]:
        """
        Returns configuration dictionary
        """
        return self._configs

    @property
    def root_path(self) -> str:
        """
        Returns root path of application
        """
        return self._root_path

    @property
    def app(self):
        """
        Returns self
        For compatibility with the Controller class
        which contains the app object on the app property
        """
        return self

    @property
    def static_files_path(self) -> str:
        """Static files paths"""
        return self._static_files_path

    @property
    def version(self) -> str:
        return self.get_conf("VERSION")

    @property
    def app_name(self) -> str:
        return self.get_conf("APP_NAME")

    @property
    def logger(self):
        return self._logger

    @property
    def jinja_environment(self) -> Environment:
        return self._jinja_environment

    @property
    def request_class(self) -> Type[Request]:
        """
        Returns the Request class used by the application.
        Can be overridden in configs to provide a custom Request subclass.
        """
        return self.get_conf("REQUEST_CLASS", Request)

    @property
    def response_class(self) -> Type[Response]:
        """
        Returns the Response class used by the application.
        Can be overridden in configs to provide a custom Response subclass.
        """
        return self.get_conf("RESPONSE_CLASS", Response)

    @property
    def extensions(self) -> "dict[str, BaseExtension]":
        """Returns dictionary with all registered extensions"""
        return self._extensions

    async def __call__(self, scope, receive, send):
        """
        Once built, __call__ just delegates to the fully wrapped app.
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
        Handles websocket requests
        """
        method: str = "SOCKET"
        url_path: str = scope["path"]
        self._log_request(scope, method, url_path)

        route_handler, path_kwargs = self._socket_router.match(url_path, method)
        if not route_handler:
            await send({"type": "websocket.close", "code": 1000})
            return
        req = Request(scope, receive, self, path_kwargs, cast(Callable, route_handler))
        req.set_send(send)
        try:
            await run_sync_or_async(route_handler, req, **path_kwargs)
        # pylint: disable-next=W0718
        except Exception as exc:
            await send(
                {
                    "type": "websocket.close",
                    "code": 1011,
                    "reason": "Internal server error",
                }
            )
            self.logger.critical(
                f"Unhandled critical error in websocket: ({req.method}) {req.path}, {req.route_parameters}: {exc}"
            )
            raise exc
