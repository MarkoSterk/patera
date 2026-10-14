"""
Base configuration class
"""

from __future__ import annotations

from typing import Optional, Sequence
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .logging.logger_config_base import DefaultLoggerConfig
from .logging.log_files import LogFilesConfig
from .request import Request
from .response import Response


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(
        extra="allow",
        env_file_encoding="utf-8",
        env_prefix="PATERA_",
        env_nested_delimiter="__",
        # PATERA_MAIN_DB__DATABASE_URI=... changes one field of a nested
        # default (MAIN_DB = SqlDatabaseConfig(...)) and keeps the others.
        nested_model_default_partial_update=True,
    )
    APP_PACKAGE: str = Field(
        "app", description="Python package where app code is located. Default is 'app'."
    )
    APP_NAME: str = Field("Patera app", description="Human-readable name of the app")
    VERSION: str = Field("1.0", description="Application version")
    # required
    BASE_PATH: str = Field(
        description="Base path of app. Hardcoded in env file or os.path.dirname(__file__) in the configs.py is the usual value."
    )

    REQUEST_CLASS: type[Request] = Field(
        Request,
        description="Request class to use. Must be a subclass of patera.request.Request",
    )
    RESPONSE_CLASS: type[Response] = Field(
        Response,
        description="Response class to use. Must be a subclass of patera.response.Response",
    )

    # optionals with sensible defaults
    DEBUG: bool = Field(True, description="If the app should run in debug mode or not.")
    HOST: str = Field(
        "localhost",
        description=(
            "Host the server listens on. `patera dev`/`patera prod` read it from "
            "PATERA_HOST or this class; production turns localhost into 0.0.0.0."
        ),
    )
    PORT: int = Field(
        3000,
        description=(
            "Port the server listens on. `patera dev` defaults to 3000 and "
            "`patera prod` to 80 unless PATERA_PORT or this class sets it."
        ),
    )
    STARTUP_BANNER: bool = Field(
        True,
        description=(
            "Print the Patera banner and address box to the console when the app "
            "starts. The startup line is always logged."
        ),
    )
    BACKGROUND_TASKS_SHUTDOWN_TIMEOUT: Optional[float] = Field(
        10.0,
        ge=0,
        description=(
            "Seconds to wait on shutdown for tasks started with "
            "run_in_background() before cancelling them (None: no limit)."
        ),
    )
    PROTOCOL: str = Field("http", description="Protocol to use in URLs, http or https")
    LIFESPAN: str = Field(
        "on",
        description=(
            "Whether to use server lifespan events/signals (on, auto, off). For use "
            "in custom run scripts; 'patera dev' and 'patera prod' always enable lifespan."
        ),
    )
    TEMPLATES_DIR: str = Field(
        "templates", description="Relative templates dir from root"
    )
    AUTO_RELOAD: bool = Field(
        True,
        description=(
            "Some loaders load templates from locations where the template sources "
            "may change (ie: file system or database).  If auto_reload is set to True "
            "(default) every time a template is requested the loader checks if the source "
            "changed and if yes, it will reload the template.  For higher performance "
            "it's possible to disable that."
        ),
    )

    STATIC_DIR: str = Field("static", description="Relative static dir from root")
    STATIC_URL: str = Field("/static", description="URL prefix for static files")
    STATIC_CONTROLLER_NAME: str = Field(
        "static",
        description="url_for alias of the static files controller (url_for('static', filename='a.css'))",
    )

    USE_STATIC_PAGES: bool = Field(
        False,
        description=(
            "Whether to use the built-in static pages controller. If True, it will serve "
            "HTML files from the directory specified in STATIC_PAGES_DIR at the URL prefix "
            "specified in STATIC_PAGES_URL. Use url_for(STATIC_PAGES_CONTROLLER_NAME, page=...) "
            "to build page URLs."
        ),
    )
    STATIC_PAGES_DIR: str = Field(
        "static_pages",
        description="Static pages directory relative to the application folder",
    )
    STATIC_PAGES_URL: str = Field("/", description="URL prefix for static pages")
    STATIC_PAGES_CONTROLLER_NAME: str = Field(
        "static_pages",
        description="url_for alias of the static pages controller (url_for('static_pages', page='about'))",
    )

    TEMPLATES_STRICT: bool = Field(True, description="Strict template rendering")
    URL_PREFIX: str = Field(
        "",
        description=(
            "Prefix of every controller route, for example '/api/v1' (empty: no "
            "prefix). Static files keep STATIC_URL."
        ),
    )
    STRICT_SLASHES: bool = Field(False, description="Route '/x' vs '/x/' strictness")
    OPEN_API: bool = Field(True, description="Enable OpenAPI endpoint")
    OPEN_API_URL: str = Field("/openapi", description="OpenAPI base path")
    OPEN_API_DESCRIPTION: str = Field("Simple API", description="OpenAPI description")
    MAX_CONTENT_LENGTH: Optional[int] = Field(
        10 * 1024 * 1024,
        ge=0,
        description=(
            "Largest accepted request body in bytes (default 10 MB), for JSON, "
            "form and multipart bodies alike. Larger requests are answered with "
            "413. None disables the limit. A request may lower or raise it "
            "through Request.max_content_length."
        ),
    )

    # CORS settings
    CORS_ENABLED: bool = Field(True, description="Enable CORS")
    CORS_ALLOW_ORIGINS: Sequence[str] = Field(
        ["*"], description="List of allowed origins"
    )
    CORS_ALLOW_METHODS: Sequence[str] = Field(
        ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="List of allowed methods",
    )
    CORS_ALLOW_HEADERS: Sequence[str] = Field(
        ["Authorization", "Content-Type"], description="List of allowed headers"
    )
    CORS_EXPOSE_HEADERS: Sequence[str] = Field([], description="Expose headers")
    CORS_ALLOW_CREDENTIALS: bool = Field(
        False,
        description=(
            "Allow credentials (cookies, Authorization) on cross-origin requests; "
            "list CORS_ALLOW_ORIGINS explicitly when turning it on"
        ),
    )
    CORS_MAX_AGE: Optional[int] = Field(
        None, description="Max age in seconds. None to disable."
    )

    DEFAULT_LOGGER: DefaultLoggerConfig = Field(
        default_factory=lambda: DefaultLoggerConfig.model_validate({}),
        description="Default patera logger configuration",
    )

    LOG_FILES: LogFilesConfig = Field(
        default_factory=lambda: LogFilesConfig.model_validate({}),
        description=(
            "JSON Lines log files. Every record is one JSON object per line; "
            "the Admin dashboard reads recent records from these files."
        ),
    )

    CONTROLLER_FOLDERS: Optional[Sequence[str]] = Field(
        None, description="List of additional folders to load controllers from"
    )
    CLI_CONTROLLER_FOLDERS: Optional[Sequence[str]] = Field(
        None, description="List of additional folders to load cli controllers from"
    )
    EXCEPTION_HANDLER_FOLDERS: Optional[Sequence[str]] = Field(
        None, description="List of additional folders to load exception handlers from"
    )
    MIDDLEWARE_FOLDERS: Optional[Sequence[str]] = Field(
        None, description="List of additional folders to load middleware from"
    )
    LOGGER_FOLDERS: Optional[Sequence[str]] = Field(
        None, description="List of additional folders to load loggers from"
    )

    @field_validator(
        "CONTROLLER_FOLDERS",
        "CLI_CONTROLLER_FOLDERS",
        "EXCEPTION_HANDLER_FOLDERS",
        "MIDDLEWARE_FOLDERS",
        "LOGGER_FOLDERS",
        mode="before",
    )
    @classmethod
    def _coerce_list_of_str(cls, v):
        if v is None:
            return None
        if not isinstance(v, Sequence) or isinstance(v, (str, bytes)):
            raise TypeError("Must be a sequence[str] or None.")
        if any(not isinstance(x, str) for x in v):
            raise TypeError("Must be a sequence[str] or None.")
        return list(v)

    @field_validator("URL_PREFIX")
    @classmethod
    def _normalize_url_prefix(cls, value: str) -> str:
        """'/api/v1/' becomes '/api/v1' and '/' becomes ''."""
        value = value.strip()
        if value and not value.startswith("/"):
            raise ValueError(f"URL_PREFIX must start with '/', got {value!r}.")
        return value.rstrip("/")

    @staticmethod
    def value_to_bool(value: str | int | bool) -> bool:
        """
        Turns a boolean-like value to boolean.

        :param str value: a string value representing a boolean

        Returns True if value in [True, "true", "True", "1", 1]
        """
        return value in [True, "true", "True", "1", 1]
