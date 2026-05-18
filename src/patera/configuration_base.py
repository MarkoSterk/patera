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
    model_config = SettingsConfigDict(
        extra="allow",
        env_file_encoding="utf-8",
        env_prefix="PATERA_",
        env_nested_delimiter="__",
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
    HOST: str = Field("localhost", description="Host ip where the app should run.")
    PORT: int = Field(3000, description="Port on which the app should run.")
    LIFESPAN: str = Field(
        "on",
        description="Whether to use server lifespan events/signals. Options: on, auto, off",
    )
    TEMPLATES_DIR: str = Field(
        "/templates", description="Relative templates dir from root"
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

    STATIC_DIR: str = Field("/static", description="Relative static dir from root")
    STATIC_URL: str = Field("/static", description="URL prefix for static files")
    STATIC_CONTROLLER_NAME: str = Field(
        "static", description="Mount name for static files controller"
    )
    TEMPLATES_STRICT: bool = Field(True, description="Strict template rendering")
    STRICT_SLASHES: bool = Field(False, description="Route '/x' vs '/x/' strictness")
    OPEN_API: bool = Field(True, description="Enable OpenAPI endpoint")
    OPEN_API_URL: str = Field("/openapi", description="OpenAPI base path")
    OPEN_API_DESCRIPTION: str = Field("Simple API", description="OpenAPI description")

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
    CORS_ALLOW_CREDENTIALS: bool = Field(True, description="Allow credentials")
    CORS_MAX_AGE: Optional[int] = Field(
        None, description="Max age in seconds. None to disable."
    )

    DEFAULT_LOGGER: dict[str, Any] = Field(
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
        description="Default patera logger configuration",
    )

    IN_MEMORY_LOG_BUFFER_SIZE: int = Field(
        1000,
        description=(
            "The size of the in-memory log message deque list. "
            "Log messages are stored in-memory for later view in "
            "the admin dashboard or elsewhere."
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

    @staticmethod
    def value_to_bool(value: str | int | bool) -> bool:
        """
        Turns a boolean-like value to boolean.

        :param str value: a string value representing a boolean

        Returns True if value in [True, "true", "True", "1", 1]
        """
        return value in [True, "true", "True", "1", 1]
