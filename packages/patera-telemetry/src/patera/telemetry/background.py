"""
Background work in a trace of its own, linked to the request that started it.
"""

from __future__ import annotations

from asyncio import Task
from typing import Any, Callable

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Link, SpanKind

from patera import run_in_background, run_sync_or_async

from .extension import INSTRUMENTATION_NAME, __version__


def run_traced_in_background(
    name: str, func: Callable[..., Any], *args: Any, **kwargs: Any
) -> Task:
    """
    Like ``patera.run_in_background``, with the work recorded as the span
    ``name`` in a new trace that links to the current span.

    A plain background task inherits the request's trace, so its spans hang
    under a request span that may have ended long before; a trace of its own
    with a link keeps both readable.
    """
    current = trace.get_current_span().get_span_context()
    links = [Link(current)] if current.is_valid else []
    tracer = trace.get_tracer(INSTRUMENTATION_NAME, __version__)

    async def traced() -> Any:
        with tracer.start_as_current_span(
            name,
            context=otel_context.Context(),
            kind=SpanKind.INTERNAL,
            links=links,
        ):
            return await run_sync_or_async(func, *args, **kwargs)

    return run_in_background(traced)
