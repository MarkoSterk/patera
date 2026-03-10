"""
Base configuration class
"""

from __future__ import annotations

import re
from typing import Optional, Any, Sequence
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .logging.logger_config_base import OutputSink
from .request import Request
from .response import Response

IMPORT_STR_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$")


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="allow")

    # required
    APP_NAME: str = Field(description="Human-readable name of the app")
    VERSION: str = Field(description="Application version")
    BASE_PATH: str = Field(
        description="Base path of app. os.path.dirname(__file__) in the configs.py is the usual value."
    )

    REQUEST_CLASS: Optional[type[Request]] = Field(
        Request,
        description="Request class to use. Must be a subclass of pyjolt.request.Request",
    )
    RESPONSE_CLASS: Optional[type[Response]] = Field(
        Response,
        description="Response class to use. Must be a subclass of pyjolt.response",
    )

    # required for Authentication extension
    SECRET_KEY: Optional[str] = Field(
        None, description="High entropy random string for signing cookies/jwts"
    )

    # optionals with sensible defaults
    DEBUG: Optional[bool] = Field(
        True, description="If the app should run in debug mode or not."
    )
    HOST: Optional[str] = Field(
        "localhost", description="Host ip where the app should run."
    )
    PORT: Optional[int] = Field(3000, description="Port on which the app should run.")
    LIFESPAN: Optional[str] = Field(
        "on",
        description="Whether to use server lifespan events/signals. Options: on, auto, off",
    )
    TEMPLATES_DIR: Optional[str] = Field(
        "/templates", description="Relative templates dir from root"
    )
    AUTO_RELOAD: Optional[bool] = Field(
        True,
        description=(
            "Some loaders load templates from locations where the template sources "
            "may change (ie: file system or database).  If auto_reload is set to True "
            "(default) every time a template is requested the loader checks if the source "
            "changed and if yes, it will reload the template.  For higher performance "
            "it's possible to disable that."
        ),
    )
    STATIC_DIR: Optional[str] = Field(
        "/static", description="Relative static dir from root"
    )
    STATIC_URL: Optional[str] = Field(
        "/static", description="URL prefix for static files"
    )
    STATIC_CONTROLLER_NAME: Optional[str] = Field(
        "static", description="Mount name for static files controller"
    )
    TEMPLATES_STRICT: Optional[bool] = Field(
        True, description="Strict template rendering"
    )
    STRICT_SLASHES: Optional[bool] = Field(
        False, description="Route '/x' vs '/x/' strictness"
    )
    OPEN_API: Optional[bool] = Field(True, description="Enable OpenAPI endpoint")
    OPEN_API_URL: Optional[str] = Field("/openapi", description="OpenAPI base path")
    OPEN_API_DESCRIPTION: Optional[str] = Field(
        "Simple API", description="OpenAPI description"
    )

    # CORS settings
    CORS_ENABLED: Optional[bool] = Field(True, description="Enable CORS")
    CORS_ALLOW_ORIGINS: Optional[Sequence[str]] = Field(
        ["*"], description="List of allowed origins"
    )
    CORS_ALLOW_METHODS: Optional[Sequence[str]] = Field(
        ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="List of allowed methods",
    )
    CORS_ALLOW_HEADERS: Optional[Sequence[str]] = Field(
        ["Authorization", "Content-Type"], description="List of allowed headers"
    )
    CORS_EXPOSE_HEADERS: Optional[Sequence[str]] = Field(
        [], description="Expose headers"
    )
    CORS_ALLOW_CREDENTIALS: Optional[bool] = Field(
        True, description="Allow credentials"
    )
    CORS_MAX_AGE: Optional[int] = Field(
        None, description="Max age in seconds. None to disable."
    )

    DEFAULT_LOGGER: Optional[dict[str, Any]] = Field(
        {
            "SINK": OutputSink.STDERR,
            "LEVEL": "TRACE",
            "FORMAT": (
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level}</level> | "
                "{extra[logger_name]} | "
                "<level>{message}</level>"
            ),
            "ROTATION": None,
            "RETENTION": None,
            "COMPRESSION": None,
            "ENQUEUE": True,
            "BACKTRACE": True,
            "DIAGNOSE": True,
            "COLORIZE": True,
            "SERIALIZE": False,
            "ENCODING": "utf-8",
            "MODE": "a",
            "DELAY": True,
        },
        description="Default pyjolt logger configuration",
    )

    IN_MEMORY_LOG_BUFFER_SIZE: int = Field(
        1000,
        description=(
            "The size of the in-memory log message deque list. "
            "Log messages are stored in-memory for later view in "
            "the admin dashboard or elsewhere."
        ),
    )

    # controllers, cli_controllers, extensions, models, exception handlers and middleware to load
    CONTROLLERS: Optional[Sequence[str]] = None
    CLI_CONTROLLERS: Optional[Sequence[str]] = None
    EXTENSIONS: Optional[Sequence[str]] = None
    MODELS: Optional[Sequence[str]] = None
    EXCEPTION_HANDLERS: Optional[Sequence[str]] = None
    MIDDLEWARE: Optional[Sequence[str]] = None
    LOGGERS: Optional[Sequence[str]] = None

    @field_validator(
        "CONTROLLERS",
        "CLI_CONTROLLERS",
        "EXTENSIONS",
        "MODELS",
        "EXCEPTION_HANDLERS",
        "MIDDLEWARE",
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

    @field_validator(
        "CONTROLLERS",
        "CLI_CONTROLLERS",
        "EXTENSIONS",
        "MODELS",
        "EXCEPTION_HANDLERS",
        "MIDDLEWARE",
    )
    @classmethod
    def _validate_import_strings(cls, v):
        if not v:
            return v
        bad = [s for s in v if not IMPORT_STR_RE.match(s)]
        if bad:
            raise ValueError(
                "Invalid import strings (use 'package.module:ClassOrObject'): "
                + ", ".join(bad)
            )
        return v

    @staticmethod
    def value_to_bool(value: str | int | bool) -> bool:
        """
        Turns a boolean-like value to boolean.

        :param str value: a string value representing a boolean

        Returns True if value in [True, "true", "True", "1", 1]
        """
        return value in [True, "true", "True", "1", 1]
