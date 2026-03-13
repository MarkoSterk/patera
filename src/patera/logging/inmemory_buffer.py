"""
In-memory log buffer
"""

from collections import deque
from threading import Lock
from typing import Deque, Dict, Any, List


class InMemoryLogBuffer:
    """
    Callable Loguru sink that stores recent log records in memory.

    - Uses a bounded deque so memory doesn't grow indefinitely.
    - Thread-safe with a simple Lock.
    """

    def __init__(self, maxlen: int = 1000):
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self._severe_buffer: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = Lock()

    def __call__(self, message):  # type: ignore[override]
        record = message.record
        data = {
            "time": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "logger_name": record["extra"].get("logger_name"),
            "file": record["file"].name,
            "line": record["line"],
            "name": record["name"],
            "function": record["function"],
        }

        with self._lock:
            self._buffer.append(data)

        if record["level"].name in ["ERROR", "CRITICAL", "FATAL"]:
            with self._lock:
                self._severe_buffer.append(data)

    def get_last(self, n: int = 100) -> List[Dict[str, Any]]:
        """Return last n records (newest last)."""
        with self._lock:
            if n >= len(self._buffer):
                return list(self._buffer)
            return list(self._buffer)[-n:]

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._buffer)

    def get_last_severe(self, n: int = 100) -> List[Dict[str, Any]]:
        """Return last n records (newest last)."""
        with self._lock:
            if n >= len(self._severe_buffer):
                return list(self._severe_buffer)
            return list(self._severe_buffer)[-n:]

    def get_severe(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._severe_buffer)
