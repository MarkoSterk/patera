"""
Request statistics for the Admin dashboard.

Admin observes every HTTP request the application finishes (see
``Patera.add_request_observer``) and keeps the last 24 hours in memory:
counts by status class, response times and, per minute, the routes and
error statuses. Each worker process keeps its own statistics, which start
again when the process restarts.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from patera.request_record import RequestRecord

RETENTION_SECONDS = 24 * 3600
BUCKET_SECONDS = 10
ROUTE_BUCKET_SECONDS = 60

# Upper bounds, in milliseconds, of the response-time histogram's bins; the
# last bin collects everything slower.
LATENCY_BOUNDS_MS = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)

STATUS_CLASSES = ("2xx", "3xx", "4xx", "5xx")

# period name -> (length in seconds, chart step in seconds)
PERIODS: dict[str, tuple[int, int]] = {
    "15m": (900, 10),
    "1h": (3600, 60),
    "6h": (21600, 300),
    "24h": (86400, 1200),
}

NO_ROUTE = "(no route)"
TOP_ROUTES = 10
TOP_ERRORS = 10
ROUTES_PER_ERROR = 3


def _status_class(status_code: int) -> Optional[str]:
    if 200 <= status_code < 600:
        return f"{status_code // 100}xx"
    return None


def _latency_bin(duration_ms: float) -> int:
    for index, bound in enumerate(LATENCY_BOUNDS_MS):
        if duration_ms <= bound:
            return index
    return len(LATENCY_BOUNDS_MS)


def percentile(histogram: list[int], fraction: float) -> Optional[float]:
    """
    The response time below which ``fraction`` of the requests fall, in
    milliseconds, interpolated within its histogram bin. Requests slower
    than the last bound report that bound.
    """
    total = sum(histogram)
    if total == 0:
        return None
    target = fraction * total
    seen = 0
    for index, count in enumerate(histogram):
        if count and seen + count >= target:
            if index >= len(LATENCY_BOUNDS_MS):
                return float(LATENCY_BOUNDS_MS[-1])
            lower = 0.0 if index == 0 else float(LATENCY_BOUNDS_MS[index - 1])
            upper = float(LATENCY_BOUNDS_MS[index])
            return lower + (upper - lower) * (target - seen) / count
        seen += count
    return float(LATENCY_BOUNDS_MS[-1])


@dataclass
class _Bucket:
    count: int = 0
    classes: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(STATUS_CLASSES, 0)
    )
    duration_ms: float = 0.0
    histogram: list[int] = field(
        default_factory=lambda: [0] * (len(LATENCY_BOUNDS_MS) + 1)
    )

    def add(self, other: "_Bucket") -> None:
        self.count += other.count
        for key, value in other.classes.items():
            self.classes[key] += value
        self.duration_ms += other.duration_ms
        for index, value in enumerate(other.histogram):
            self.histogram[index] += value


@dataclass
class _RouteBucket:
    # (method, route) -> [requests, 4xx, 5xx, total milliseconds]
    routes: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    # status code -> route -> requests
    errors: dict[int, dict[str, int]] = field(default_factory=dict)


class RequestStats:
    """
    In-memory request statistics of one process for the last 24 hours, in
    10-second buckets (counts and response times) and 1-minute buckets
    (routes and error statuses).
    """

    def __init__(self, started_at: Optional[float] = None) -> None:
        self.started_at: float = started_at if started_at is not None else time.time()
        self._lock = threading.Lock()
        self._buckets: dict[int, _Bucket] = {}
        self._bucket_keys: deque[int] = deque()
        self._route_buckets: dict[int, _RouteBucket] = {}
        self._route_keys: deque[int] = deque()

    def mark_started(self, started_at: Optional[float] = None) -> None:
        self.started_at = started_at if started_at is not None else time.time()

    def observe(self, record: RequestRecord) -> None:
        """Counts one finished request. Requests without a response are skipped."""
        if record.status_code is None:
            return
        status_class = _status_class(record.status_code)
        duration_ms = record.duration * 1000
        route = record.route or NO_ROUTE
        with self._lock:
            bucket = self._bucket(int(record.started_at // BUCKET_SECONDS))
            bucket.count += 1
            if status_class in bucket.classes:
                bucket.classes[status_class] += 1
            bucket.duration_ms += duration_ms
            bucket.histogram[_latency_bin(duration_ms)] += 1

            routes = self._route_bucket(int(record.started_at // ROUTE_BUCKET_SECONDS))
            entry = routes.routes.setdefault((record.method, route), [0, 0, 0, 0.0])
            entry[0] += 1
            if status_class == "4xx":
                entry[1] += 1
            elif status_class == "5xx":
                entry[2] += 1
            entry[3] += duration_ms
            if record.status_code >= 400:
                by_route = routes.errors.setdefault(record.status_code, {})
                by_route[route] = by_route.get(route, 0) + 1

    def _bucket(self, key: int) -> _Bucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = _Bucket()
            self._bucket_keys.append(key)
            self._prune(
                self._buckets,
                self._bucket_keys,
                key - RETENTION_SECONDS // BUCKET_SECONDS,
            )
        return bucket

    def _route_bucket(self, key: int) -> _RouteBucket:
        bucket = self._route_buckets.get(key)
        if bucket is None:
            bucket = self._route_buckets[key] = _RouteBucket()
            self._route_keys.append(key)
            self._prune(
                self._route_buckets,
                self._route_keys,
                key - RETENTION_SECONDS // ROUTE_BUCKET_SECONDS,
            )
        return bucket

    @staticmethod
    def _prune(buckets: dict[int, Any], keys: deque[int], oldest: int) -> None:
        while keys and keys[0] < oldest:
            buckets.pop(keys.popleft(), None)

    def summary(
        self, period: str = "1h", now: Optional[float] = None
    ) -> dict[str, Any]:
        """The statistics of the last ``period`` (a key of ``PERIODS``), as JSON data."""
        seconds, step = PERIODS[period]
        now = time.time() if now is None else now
        end = (int(now) // step + 1) * step
        start = end - seconds
        with self._lock:
            series, total = self._series(start, end, step)
            routes, errors = self._routes(start, end)
        observed = max(min(now - start, now - self.started_at), 1)
        return {
            "period": period,
            "step": step,
            "now": now,
            "started_at": self.started_at,
            "uptime": max(now - self.started_at, 0),
            "since": max(start, self.started_at),
            "totals": {
                "requests": total.count,
                **total.classes,
                "average_rps": total.count / observed,
                "average_ms": total.duration_ms / total.count if total.count else None,
                "p95_ms": percentile(total.histogram, 0.95),
            },
            "series": series,
            "routes": routes,
            "errors": errors,
        }

    def _series(
        self, start: int, end: int, step: int
    ) -> tuple[list[dict[str, Any]], _Bucket]:
        total = _Bucket()
        series = []
        for point_start in range(start, end, step):
            point = _Bucket()
            first = point_start // BUCKET_SECONDS
            for key in range(first, first + step // BUCKET_SECONDS):
                bucket = self._buckets.get(key)
                if bucket is not None:
                    point.add(bucket)
            total.add(point)
            series.append(
                {
                    "time": point_start,
                    "rps": {key: value / step for key, value in point.classes.items()},
                    "requests": point.count,
                    "average_ms": point.duration_ms / point.count
                    if point.count
                    else None,
                    "p95_ms": percentile(point.histogram, 0.95),
                }
            )
        return series, total

    def _routes(
        self, start: int, end: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        routes: dict[tuple[str, str], list[float]] = {}
        errors: dict[int, dict[str, int]] = {}
        for key in range(
            start // ROUTE_BUCKET_SECONDS, end // ROUTE_BUCKET_SECONDS + 1
        ):
            bucket = self._route_buckets.get(key)
            if bucket is None:
                continue
            for route_key, values in bucket.routes.items():
                entry = routes.setdefault(route_key, [0, 0, 0, 0.0])
                for index, value in enumerate(values):
                    entry[index] += value
            for status_code, by_route in bucket.errors.items():
                merged = errors.setdefault(status_code, {})
                for route, count in by_route.items():
                    merged[route] = merged.get(route, 0) + count
        busiest = sorted(routes.items(), key=lambda item: (-item[1][0], item[0]))
        frequent = sorted(
            errors.items(), key=lambda item: (-sum(item[1].values()), item[0])
        )
        return (
            [
                {
                    "method": method,
                    "route": route,
                    "requests": int(values[0]),
                    "4xx": int(values[1]),
                    "5xx": int(values[2]),
                    "average_ms": values[3] / values[0],
                }
                for (method, route), values in busiest[:TOP_ROUTES]
            ],
            [
                {
                    "status": status_code,
                    "requests": sum(by_route.values()),
                    "routes": [
                        {"route": route, "requests": count}
                        for route, count in sorted(
                            by_route.items(), key=lambda item: (-item[1], item[0])
                        )[:ROUTES_PER_ERROR]
                    ],
                }
                for status_code, by_route in frequent[:TOP_ERRORS]
            ],
        )
