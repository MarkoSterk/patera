from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# Loguru's standard levels, lowest first.
LOG_LEVELS: dict[str, int] = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "SUCCESS": 25,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


# Columns the dashboard can be sorted by ("-" prefix: descending).
LOG_ORDER_COLUMNS: tuple[str, ...] = (
    "time",
    "level",
    "logger_name",
    "name",
    "file",
    "line",
    "function",
)


class LogsQuerySchema(BaseModel):
    count: int = Field(50, description="Number of log messages to display")
    severity: str = Field(
        "INFO",
        description="Severity of messages to display. Everything equal to or above.",
    )
    page: int = Field(1, description="Page to display.")
    query: Optional[str] = Field(
        None, description="String to look for in query messages"
    )
    order_by: str = Field("-time", description="Ordering of log messages by time")

    @field_validator("order_by", mode="before")
    @classmethod
    def _known_column(cls, value: Any) -> str:
        """Unknown columns fall back to newest first."""
        text = str(value or "").strip()
        return text if text.removeprefix("-") in LOG_ORDER_COLUMNS else "-time"

    @field_validator("severity", mode="before")
    @classmethod
    def _known_severity(cls, value: Any) -> str:
        """Accepts level names in any case; unknown names fall back to INFO."""
        name = str(value or "").strip().upper()
        return name if name in LOG_LEVELS else "INFO"


def level_at_least(record: dict[str, Any], severity: str) -> bool:
    """
    True if the record's level is ``severity`` or higher. Records with a
    custom level that has no known rank are always shown.
    """
    rank = LOG_LEVELS.get(str(record.get("level", "")).upper())
    return rank is None or rank >= LOG_LEVELS[severity]


def log_sort_key(record: dict[str, Any], column: str) -> tuple[Any, ...]:
    """
    Sort key for a log record. Levels sort by severity (custom levels
    without a known rank first, by name), lines numerically, and other
    columns as text; records missing the value sort first. Ties are broken
    by time.
    """
    value = record.get(column)
    time = str(record.get("time") or "")
    if column == "level":
        name = str(value or "").upper()
        return (LOG_LEVELS.get(name, -1), name, time)
    if column == "line":
        try:
            return (1, int(value), time) if value is not None else (0, 0, time)
        except (TypeError, ValueError):
            return (0, 0, time)
    return (0 if value is None else 1, "" if value is None else str(value), time)
