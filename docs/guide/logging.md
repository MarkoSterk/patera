# Logging

Patera logs with [Loguru](https://loguru.readthedocs.io). Use `self.app.logger` in controllers
and services (or `app.logger`).

```python
self.app.logger.info("Note created")
self.app.logger.bind(note_id=note.id).warning("Note title truncated")
```

## The default sink

The default console sink is configured with `DEFAULT_LOGGER`, a `DefaultLoggerConfig` model.
Fields you leave out keep their defaults, and unknown fields are rejected:

```python
from patera.logging import DefaultLoggerConfig


class Config(BaseConfig):
    ...
    DEFAULT_LOGGER: DefaultLoggerConfig = DefaultLoggerConfig(
        SINK="STDERR",             # STDERR, STDOUT, NULL or a file path
        LEVEL="INFO",
        ENQUEUE=True,
        COLORIZE=True,
    )
```

Fields can also be set from the environment, for example `PATERA_DEFAULT_LOGGER__LEVEL=INFO`.

## Log files

Every record at `LOG_FILES.LEVEL` or above is also written to a JSON Lines file, one JSON object
per line with `time`, `level`, `message`, `logger_name`, `name`, `file`, `line`, `function`,
`process`, `thread`, and, when present, `exception` (the formatted traceback) and `extra` (values
bound with `logger.bind(...)`). The [admin dashboard](../extensions/admin.md) reads its log view
from these files.

```python
from patera.logging import LogFilesConfig


class Config(BaseConfig):
    ...
    LOG_FILES: LogFilesConfig = LogFilesConfig(
        PATH="logs/patera.jsonl",  # relative to the application package; must end with .jsonl
        LEVEL="INFO",
        ROTATION="10 MB",          # size, time of day ("00:00") or interval ("1 day"); None = never
        FILE_COUNT=5,              # files kept, including the active one
    )
```

| Field | Default | Description |
|-------|---------|-------------|
| `ENABLED` | `True` | Write log files. |
| `PATH` | `logs/patera.jsonl` | Active file. Rotated files are renamed with their rotation time, e.g. `patera.2026-10-09_13-25-00_123456.jsonl`. |
| `LEVEL` | `DEBUG` | Minimum level written. |
| `ROTATION` | `10 MB` | When the active file is rotated. |
| `FILE_COUNT` | `5` | Number of files kept; older rotated files are deleted. |
| `ENQUEUE` | `True` | Write from a background queue. |
| `READ_LIMIT` | `10000` | Maximum number of newest records returned by `app.log_files.read()`. |

`app.log_files.read(limit)` (or `await app.log_files.read_async(limit)`) returns the newest
records, oldest first.

!!! warning "Several workers"

    Rotation is not coordinated between processes. With several server workers appending to one
    file, set `ROTATION=None` and rotate with an external tool, or run a single worker.

## Custom sinks

Additional sinks are classes in a `logging` / `loggers` folder (file name containing `logger`,
`log_sink` or `logging`):

```python
# app/loggers/file_logger.py
from patera.logging import LoggerBase, logger


@logger("File logger")
class FileLogger(LoggerBase):
    def get_filter(self):
        return lambda record: record["level"].no >= 30   # WARNING and above
```

Its settings are read from the config field named after the class:

```python
class Config(BaseConfig):
    ...
    FILE_LOGGER: dict[str, Any] = {
        "SINK": "logs/app.log",     # relative to the application package
        "LEVEL": "WARNING",
        "ROTATION": "5 MB",
        "RETENTION": "10 days",
        "COMPRESSION": "zip",
    }
```

Override the sink getters as needed; `configs_model` selects the settings model. Loguru is
process-global, so applications in the same process share its sinks.

!!! note

    Built-in request logging includes the query string. Redact at the logging boundary or avoid
    sensitive URL parameters.

## Request observers

For HTTP metrics, register an observer, typically from a service listed in `app_extensions`:

```python
from typing import TYPE_CHECKING

from patera import RequestRecord, Service

if TYPE_CHECKING:
    from app import App


class RequestMetrics(Service["App"]):
    def init(self):
        self.app.add_request_observer(self.observe)

    def observe(self, record: RequestRecord):
        if record.duration > 1:
            self.app.logger.warning(f"Slow request: {record.method} {record.path}")
```

- Observers see static requests and routing failures that middleware misses, and run after the
  response is sent.
- Records include the method, path, matched route (or `None`), sent status, start time and
  duration in seconds.
- Keep callbacks quick. Failures are logged and skipped, and an observer cannot change the response.
