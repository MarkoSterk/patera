"""
Base logger configuration class
"""

import sys
import re
from abc import ABC
from datetime import timedelta
from pathlib import Path
from typing import (
    Dict,
    Any,
    Union,
    Optional,
    ClassVar,
    cast,
    TYPE_CHECKING,
    IO,
    Callable,
    Protocol,
    runtime_checkable,
    Type,
    TypedDict,
    NotRequired,
)
from enum import StrEnum
from pydantic import BaseModel, field_validator, Field, ConfigDict

from loguru import logger

if TYPE_CHECKING:
    from ..pyjolt import PyJolt


@runtime_checkable
# pylint: disable=R0903
class Writable(Protocol):
    def write(self, s: str) -> Any: ...


SinkType = Union[str, Path, IO[str], IO[bytes], Callable[[str], Any]]
SinkInput = Union[str, Path, IO[str], IO[bytes], Callable[[str], Any], Writable]
SinkAccepted = Union[str, Writable, Callable[[str], None]]
RotationType = Union[str, int, timedelta, Callable[[str, Any], Any]]
RetentionType = Union[str, int, timedelta, Callable[[str, Any], Any]]
CompressionType = Optional[str]
FilterType = Union[None, str, Dict[str, str], Callable[[Dict[str, Any]], bool]]


class OutputSink(StrEnum):
    STDERR = "STDERR"
    STDOUT = "STDOUT"


class LogLevel(StrEnum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class _LoggerConfigBase(BaseModel):
    """
    Base config model for loggers
    """

    model_config = ConfigDict(extra="allow")

    SINK: Optional[str | Path] = Field(
        OutputSink.STDERR.value, description="Output of the logger"
    )
    LEVEL: Optional[LogLevel] = Field(
        LogLevel.TRACE, description="Log level for logger implementation"
    )
    FORMAT: Optional[str] = Field(
        "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {extra[logger_name]} | <level>{message}</level>",
        description="Output format",
    )
    ENQUEUE: Optional[bool] = Field(
        False,
        description="Use enqueue or not. For thread, process and coroutine safe logging.",
    )
    BACKTRACE: Optional[bool] = Field(True, description="Use backtrace")
    DIAGNOSE: Optional[bool] = Field(True, description="Diagnose mode")
    COLORIZE: Optional[bool] = Field(True, description="Colorize output")
    DELAY: Optional[bool] = Field(True, description="Use delay")
    ROTATION: Optional[RotationType] = Field(
        "5 MB", description="Size of log file before rotating."
    )
    RETENTION: Optional[RetentionType] = Field(
        "10 days", description="How long log files are kept before automatic erasure."
    )
    COMPRESSION: CompressionType = Field(
        "zip", description="If log files should be compressed. No compression = None"
    )
    SERIALIZE: Optional[bool] = Field(False)
    ENCODING: Optional[str] = Field(
        "utf-8", description="Encoding of logged messages - for file logging."
    )
    MODE: Optional[str] = Field(
        "a", description="If log messages should be appended to the file."
    )

    @field_validator("SINK", mode="before")
    @classmethod
    def normalize_sink(cls, v):
        """Accept case-insensitive strings and convert to canonical form."""
        s = v.strip().upper()
        if s in {"STDERR", "SYS.ERR", "CONSOLE", "ERR"}:
            return "STDERR"
        if s in {"STDOUT", "SYS.OUT", "OUT"}:
            return "STDOUT"
        if s in {"NULL", "DEVNULL", "NONE"}:
            return "NULL"
        # Otherwise treat it as a path
        return Path(v)


class LoggerConfig(TypedDict):
    SINK: NotRequired[str | Path]
    LEVEL: NotRequired[LogLevel]
    FORMAT: NotRequired[str]
    ENQUEUE: NotRequired[bool]
    BACKTRACE: NotRequired[bool]
    DIAGNOSE: NotRequired[bool]
    COLORIZE: NotRequired[bool]
    DELAY: NotRequired[bool]
    ROTATION: NotRequired[RotationType]
    RETENTION: NotRequired[RetentionType]
    COMPRESSION: NotRequired[CompressionType]
    SERIALIZE: NotRequired[bool]
    ENCODING: NotRequired[str]
    MODE: NotRequired[str]


class LoggerBase(ABC):
    """
    Base template for configuring a Loguru sink.
    Subclasses implement get_sink() and optionally override getters below.
    """

    configs_model: ClassVar[Optional[Type[_LoggerConfigBase]]] = cast(
        Type[_LoggerConfigBase], None
    )

    def __init__(self, app: "PyJolt"):
        self.app: "PyJolt" = app
        # loads configs for the logger from application configurations
        # by the config class name as upper-case
        # example: CustomLoggerConfig -> CUSTOM_LOGGER_CONFIG
        self.conf: Dict[str, Any] = app.get_conf(self.logger_name, None) or {}  # type: ignore
        self.conf = self.validate_configs(self.conf)

    def validate_configs(self, configs: dict[str, Any]) -> dict[str, Any]:
        if self.configs_model is not None and issubclass(
            self.configs_model, _LoggerConfigBase
        ):
            return self.configs_model.model_validate(configs).model_dump()
        return _LoggerConfigBase.model_validate(configs).model_dump()

    @property
    def logger_name(self) -> str:
        """Returns class name as upper snake case"""
        name = self.__class__.__name__
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()

    def get_sink(self) -> SinkInput:
        sink = self.conf.get("SINK", "STDERR")
        if sink == "STDERR":
            return sys.stderr
        if sink == "STDOUT":
            return sys.stdout
        if sink == "NULL":
            return "NUL" if sys.platform.startswith("win") else "/dev/null"
        p = Path(sink)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def get_conf_value(self, key: str, default: Any = None) -> Any:
        return self.conf.get(key, default)

    def get_level(self) -> Union[str, int]:
        return self.get_conf_value("LEVEL", LogLevel.INFO)

    def get_format(self) -> str:
        # includes the logger name as a constant-like tag
        return self.get_conf_value(
            "FORMAT",
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | {extra[logger_name]} | "
            "{name}:{function}:{line} - <cyan>{message}</cyan>",
        )

    def dict_to_format_string(self, fmt_dict: dict[str, str]) -> str:
        """
        Converts a dictionary of Loguru placeholders into a JSON-like
        format string suitable for loguru.add(format=...).

        CURRENTLY DOESN'T WORK AS INTENDED
        """
        items = []
        for key, value in fmt_dict.items():
            items.append(f'"{key}": "{value}"')
        return "{{{}}}".format(", ".join(items))

    def get_rotation(self) -> Optional[RotationType]:
        return self.get_conf_value("ROTATION", None)

    def get_retention(self) -> Optional[RetentionType]:
        return self.get_conf_value("RETENTION", None)

    def get_compression(self) -> CompressionType:
        return self.get_conf_value("COMPRESSION", None)

    def get_filter(self) -> FilterType:
        return None

    def _wrap_filter_with_logger_name(
        self, original_filter: FilterType
    ) -> Callable[[Dict[str, Any]], bool]:
        def _wrapped(record: Dict[str, Any]) -> bool:
            # Injects the logger name as extra information
            record["extra"].setdefault("logger_name", self.logger_name)

            if original_filter is None:
                return True
            if callable(original_filter):
                return bool(original_filter(record))
            if isinstance(original_filter, str):
                return record.get("name") == original_filter
            if isinstance(original_filter, dict):
                return all(
                    record["extra"].get(k) == v for k, v in original_filter.items()
                )
            return True

        return _wrapped

    def get_enqueue(self) -> bool:
        return self.get_conf_value("ENQUEUE", True)

    def get_backtrace(self) -> bool:
        return self.get_conf_value("BACKTRACE", False)

    def get_diagnose(self) -> bool:
        return self.get_conf_value("DIAGNOSE", False)

    def get_colorize(self) -> Optional[bool]:
        return self.get_conf_value("COLORIZE", None)

    def get_serialize(self) -> bool:
        return self.get_conf_value("SERIALIZE", False)

    def get_encoding(self) -> Optional[str]:
        return self.get_conf_value("ENCODING", "utf-8")

    def get_mode(self) -> Optional[str]:
        return self.get_conf_value("MODE", "a")

    def get_delay(self) -> bool:
        return self.get_conf_value("DELAY", True)

    def remove_existing_handlers(self) -> bool:
        return self.get_conf_value("remove_existing_handlers", False)

    def _build_handler_kwargs(self) -> Dict[str, Any]:
        return {
            "level": self.get_level(),
            "format": self.get_format(),
            "rotation": self.get_rotation(),
            "retention": self.get_retention(),
            "compression": self.get_compression(),
            "filter": self.get_filter(),
            "enqueue": self.get_enqueue(),
            "backtrace": self.get_backtrace(),
            "diagnose": self.get_diagnose(),
            "colorize": self.get_colorize(),
            "serialize": self.get_serialize(),
            "encoding": self.get_encoding(),
            "mode": self.get_mode(),
            "delay": self.get_delay(),
        }

    def _is_path_sink(self, sink: SinkAccepted) -> bool:
        return isinstance(sink, str)

    def _is_stream_sink(self, sink: SinkAccepted) -> bool:
        return (not isinstance(sink, str)) and hasattr(sink, "write")

    def _is_callable_sink(self, sink: SinkAccepted) -> bool:
        return callable(sink) and not hasattr(sink, "write")

    def _normalize_sink(self, sink: SinkInput) -> SinkAccepted:
        if isinstance(sink, Path):
            return sink.as_posix()
        return sink  # type: ignore[return-value]

    def _filter_kwargs_for_sink(
        self, sink: SinkAccepted, kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Common kwargs accepted by all sinks
        common = {
            "level",
            "format",
            "filter",
            "colorize",
            "serialize",
            "backtrace",
            "diagnose",
            "enqueue",
            "catch",
        }
        # File-path only kwargs (Loguru opens the file for you)
        file_only = {
            "rotation",
            "retention",
            "compression",
            "mode",
            "delay",
            "encoding",
            "buffering",
        }
        # Streams (TextIO / Writable): no rotation/retention/compression/encoding/mode/delay
        stream_only: set = set()  # (no extra)
        # Callables: also no file-only kwargs
        callable_only: set = set()

        if self._is_path_sink(sink):
            allowed = common | file_only
        elif self._is_stream_sink(sink):
            allowed = common | stream_only
        else:  # callable sink
            allowed = common | callable_only

        return {k: v for k, v in kwargs.items() if k in allowed and v is not None}

    def configure(self) -> int:

        raw_sink = self.get_sink()
        sink = self._normalize_sink(raw_sink)

        base_kwargs = self._build_handler_kwargs()
        # Wrap filter to inject extra["logger_name"] for every record to this sink
        base_kwargs["filter"] = self._wrap_filter_with_logger_name(
            base_kwargs.get("filter")
        )

        kwargs = self._filter_kwargs_for_sink(sink, base_kwargs)
        logger_sink_id: int = logger.add(sink, **kwargs)

        return logger_sink_id
