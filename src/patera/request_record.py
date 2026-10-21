"""
What the application observed about one finished HTTP request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """
    One finished HTTP request, passed to every request observer.

    ``route`` is the matched URL rule, such as ``/api/exams/<exam_id>``, so
    requests to the same endpoint share it; it is None when no route matched
    (404, 405, trailing-slash redirects). ``status_code`` is the status the
    response started with, 500 when the request failed before a response
    started, and None when the client left before any response.
    """

    method: str
    path: str
    route: Optional[str]
    status_code: Optional[int]
    started_at: float
    """Wall-clock start, seconds since the epoch (``time.time()``)."""
    duration: float
    """Seconds from receiving the request until its response was sent."""


RequestObserver = Callable[[RequestRecord], None]
