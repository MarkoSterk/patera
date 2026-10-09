"""
JSON Lines log files

Every log record is written as one JSON object per line. Files rotate by size
or time, and only a configured number of files is kept. The Admin dashboard
and other viewers read the most recent records back from these files.
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import traceback
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional, Union

from loguru import logger as loguru_logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .logger_config_base import LogLevel

#: Key of the record's "extra" dictionary that carries the serialized line.
_SERIALIZED_KEY = "_patera_jsonl"

RotationSetting = Union[int, timedelta, str]


class LogFilesConfig(BaseModel):
    """
    Configuration of the application's JSON Lines log files (``LOG_FILES``).
    """

    model_config = ConfigDict(extra="forbid")

    ENABLED: bool = Field(True, description="Write log records to JSON Lines files.")
    PATH: str = Field(
        "logs/patera.jsonl",
        description=(
            "Path of the active log file. A relative path is resolved from the "
            "application root. Must end with .jsonl."
        ),
    )
    LEVEL: LogLevel = Field(
        LogLevel.DEBUG, description="Minimum level of records written to the files."
    )
    ROTATION: Optional[RotationSetting] = Field(
        "10 MB",
        description=(
            "When the active file is rotated: a size ('10 MB' or a number of bytes), "
            "a time of day ('00:00'), or an interval ('1 day', '1 week'). "
            "None disables rotation."
        ),
    )
    FILE_COUNT: int = Field(
        5,
        ge=1,
        description=(
            "Number of files kept, including the active one. Older rotated "
            "files are deleted."
        ),
    )
    ENQUEUE: bool = Field(
        True,
        description="Write records from a background queue instead of the caller.",
    )
    READ_LIMIT: int = Field(
        10_000,
        ge=1,
        description="Maximum number of the newest records returned to readers.",
    )

    @field_validator("LEVEL", mode="before")
    @classmethod
    def normalize_level(cls, value: Any) -> Any:
        """Accepts case-insensitive level names from environment files."""
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("PATH")
    @classmethod
    def require_jsonl_suffix(cls, value: str) -> str:
        """Rotated files are recognised by the .jsonl suffix."""
        if Path(value).suffix.lower() != ".jsonl":
            raise ValueError("LOG_FILES.PATH must end with .jsonl")
        return value


def serialize_record(record: dict[str, Any], default_logger_name: str) -> str:
    """Returns one Loguru record as a single-line JSON object."""
    extra: dict[str, Any] = dict(record["extra"])
    extra.pop(_SERIALIZED_KEY, None)
    logger_name = extra.pop("logger_name", None) or default_logger_name

    data: dict[str, Any] = {
        "time": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "logger_name": logger_name,
        "name": record["name"],
        "file": record["file"].name,
        "line": record["line"],
        "function": record["function"],
        "process": record["process"].id,
        "thread": record["thread"].name,
    }

    exception = record["exception"]
    if exception is not None and exception.type is not None:
        data["exception"] = "".join(
            traceback.format_exception(
                exception.type, exception.value, exception.traceback
            )
        ).rstrip()

    if extra:
        data["extra"] = extra

    return json.dumps(data, ensure_ascii=False, default=str)


class JsonLogFiles:
    """
    Writes log records to rotating JSON Lines files and reads them back.

    The active file is ``PATH``. Rotated files sit next to it and carry the
    rotation time in their name, for example ``patera.2026-10-09_13-25-00_123456.jsonl``.
    """

    def __init__(
        self,
        config: LogFilesConfig,
        root_path: Union[str, Path],
        default_logger_name: str = "Patera Logger",
    ) -> None:
        self.config: LogFilesConfig = config
        path = Path(config.PATH)
        if not path.is_absolute():
            path = Path(root_path) / path
        self.path: Path = path
        self.default_logger_name: str = default_logger_name
        self._sink_id: Optional[int] = None

    @property
    def enabled(self) -> bool:
        return self.config.ENABLED

    @property
    def sink_id(self) -> Optional[int]:
        """Loguru handler id while the sink is attached."""
        return self._sink_id

    def _format(self, record: dict[str, Any]) -> str:
        record["extra"][_SERIALIZED_KEY] = serialize_record(
            record, self.default_logger_name
        )
        return "{extra[" + _SERIALIZED_KEY + "]}\n"

    def attach(self) -> Optional[int]:
        """Adds the file sink to Loguru. Returns the handler id, or None if disabled."""
        if not self.enabled:
            return None
        if self._sink_id is not None:
            return self._sink_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {
            "level": self.config.LEVEL.value,
            "format": self._format,
            "enqueue": self.config.ENQUEUE,
            "backtrace": False,
            "diagnose": False,
            "colorize": False,
            "encoding": "utf-8",
            "mode": "a",
            "delay": True,
        }
        if self.config.ROTATION is not None:
            options["rotation"] = self.config.ROTATION
            # Loguru's count retention keeps that many rotated files next
            # to the active one.
            options["retention"] = self.config.FILE_COUNT - 1
        self._sink_id = loguru_logger.add(self.path.as_posix(), **options)
        return self._sink_id

    def detach(self) -> None:
        """Removes the file sink from Loguru."""
        if self._sink_id is None:
            return
        try:
            loguru_logger.remove(self._sink_id)
        except ValueError:
            pass
        self._sink_id = None

    def files(self) -> list[Path]:
        """Existing log files, newest first; the active file comes first."""
        pattern = os.path.join(
            glob.escape(str(self.path.parent)),
            glob.escape(self.path.stem) + ".*" + glob.escape(self.path.suffix),
        )
        rotated = [Path(p) for p in glob.glob(pattern) if Path(p) != self.path]
        rotated.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        active = [self.path] if self.path.is_file() else []
        return active + rotated

    def read(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """
        Returns the newest records, oldest first. At most ``limit`` records are
        returned; the default is ``READ_LIMIT``. Lines that are not complete
        JSON objects, such as a line still being written, are skipped.
        """
        limit = self.config.READ_LIMIT if limit is None else max(limit, 0)
        newest_first: list[dict[str, Any]] = []
        for path in self.files():
            if len(newest_first) >= limit:
                break
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                if len(newest_first) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    newest_first.append(item)
        newest_first.reverse()
        return newest_first

    async def read_async(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Same as read(), but runs the file access in a worker thread."""
        return await asyncio.to_thread(self.read, limit)
