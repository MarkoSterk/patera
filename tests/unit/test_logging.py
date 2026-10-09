"""
Default logger configuration model and the JSON Lines log files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from patera import BaseConfig
from patera.logger import DefaultLogger
from patera.logging import DefaultLoggerConfig, JsonLogFiles, LogFilesConfig


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_default_logger_is_a_pydantic_model():
    configs = BaseConfig(BASE_PATH=".")
    assert isinstance(configs.DEFAULT_LOGGER, DefaultLoggerConfig)
    assert configs.DEFAULT_LOGGER.LEVEL == "TRACE"
    assert configs.DEFAULT_LOGGER.ROTATION is None
    assert isinstance(configs.LOG_FILES, LogFilesConfig)
    assert configs.LOG_FILES.PATH == "logs/patera.jsonl"


def test_logger_settings_from_nested_environment_variables(monkeypatch):
    monkeypatch.setenv("PATERA_DEFAULT_LOGGER__LEVEL", "warning")
    monkeypatch.setenv("PATERA_LOG_FILES__FILE_COUNT", "3")
    monkeypatch.setenv("PATERA_LOG_FILES__ROTATION", "1 MB")
    configs = BaseConfig(BASE_PATH=".")
    assert configs.DEFAULT_LOGGER.LEVEL == "WARNING"
    assert configs.LOG_FILES.FILE_COUNT == 3
    assert configs.LOG_FILES.ROTATION == "1 MB"


def test_logger_models_reject_unknown_keys_and_bad_values():
    with pytest.raises(ValidationError):
        DefaultLoggerConfig(LEVL="INFO")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        LogFilesConfig(PATH="logs/app.log")
    with pytest.raises(ValidationError):
        LogFilesConfig(FILE_COUNT=0)


def test_dictionary_override_uses_default_logger_defaults(make_app):
    app = make_app(DEFAULT_LOGGER={"LEVEL": "ERROR", "ENQUEUE": False})
    conf = DefaultLogger(app).conf
    assert conf["LEVEL"] == "ERROR"
    assert conf["ROTATION"] is None  # DefaultLoggerConfig default, not LoggerConfigBase
    assert conf["COLORIZE"] is True


def test_unknown_default_logger_key_fails_at_startup(make_app):
    with pytest.raises(ValidationError):
        make_app(DEFAULT_LOGGER={"LEVEL": "ERROR", "ENQUE": False})


def test_records_are_written_as_json_lines(make_app):
    app = make_app()
    app.logger.bind(request_id="abc").info("hello {}", "world")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        app.logger.exception("failed")

    path = Path(app.root_path) / "logs" / "patera.jsonl"
    assert app.log_files.path == path
    records = [r for r in _lines(path) if r["message"] in {"hello world", "failed"}]
    hello, failed = records
    assert hello["level"] == "INFO"
    assert hello["logger_name"] == "Patera Logger"
    assert hello["function"] == "test_records_are_written_as_json_lines"
    assert hello["file"] == "test_logging.py"
    assert hello["extra"] == {"request_id": "abc"}
    for key in ("time", "name", "line", "process", "thread"):
        assert key in hello
    assert failed["level"] == "ERROR"
    assert "RuntimeError: boom" in failed["exception"]
    assert "exception" not in hello


def test_level_filters_file_records(make_app):
    app = make_app(LOG_FILES={"ENQUEUE": False, "LEVEL": "WARNING"})
    app.logger.info("quiet")
    app.logger.warning("loud")
    messages = [r["message"] for r in app.log_files.read()]
    assert "loud" in messages and "quiet" not in messages


def test_rotation_keeps_the_configured_number_of_files(make_app):
    app = make_app(
        LOG_FILES={"ENQUEUE": False, "ROTATION": 1500, "FILE_COUNT": 3, "LEVEL": "INFO"}
    )
    for i in range(60):
        app.logger.info(f"message {i}")

    files = app.log_files.files()
    assert len(files) == 3
    assert files[0] == app.log_files.path
    assert all(p.suffix == ".jsonl" and p.name.startswith("patera.") for p in files)

    records = app.log_files.read()
    numbers = [
        int(r["message"].split()[1])
        for r in records
        if r["message"].startswith("message")
    ]
    assert numbers == sorted(numbers)
    assert numbers[-1] == 59
    assert numbers[0] > 0  # the oldest files were deleted

    newest = app.log_files.read(limit=5)
    assert [r["message"] for r in newest] == [f"message {i}" for i in range(55, 60)]


def test_disabled_log_files_write_nothing(make_app):
    app = make_app(LOG_FILES={"ENABLED": False})
    app.logger.error("not stored")
    assert app.log_files.sink_id is None
    assert app.log_files.read() == []
    assert not app.log_files.path.exists()


def test_reader_skips_incomplete_lines(tmp_path):
    files = JsonLogFiles(LogFilesConfig(PATH="app.jsonl"), tmp_path)
    files.path.write_text(
        '{"message": "one"}\n\n["not", "a", "record"]\n{"message": "two"}\n{"mess',
        encoding="utf-8",
    )
    assert [r["message"] for r in files.read()] == ["one", "two"]


async def test_read_async_and_shutdown_detaches_the_sink(make_app, client_for):
    app = make_app()
    async with client_for(app):
        assert app.log_files.sink_id is not None
        app.logger.info("during lifespan")
        records = await app.log_files.read_async()
        assert any(r["message"] == "during lifespan" for r in records)
    assert app.log_files.sink_id is None
