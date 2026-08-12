from __future__ import annotations

from time import monotonic
from typing import Any

import structlog
from starlette.requests import Request

logger = structlog.get_logger(__name__)


def mark_chat_phase(request: Request, phase: str, **fields: Any) -> None:
    """Record a low-cardinality timing phase for the streaming chat request.

    The helper deliberately records only phase names, durations and request/run
    identifiers. It never receives prompt content, credentials or user PII.
    Non-chat requests are ignored so normal API traffic is not instrumented.
    """
    if request.method != "POST" or request.url.path != "/api/chat":
        return
    now = monotonic()
    state = request.state
    started_at = getattr(state, "chat_timing_started_at", None)
    previous_at = getattr(state, "chat_timing_previous_at", None)
    if started_at is None:
        started_at = now
        state.chat_timing_started_at = started_at
    if previous_at is None:
        previous_at = started_at
    state.chat_timing_previous_at = now
    logger.info(
        "chat_latency_phase",
        phase=phase,
        phase_ms=round((now - previous_at) * 1000, 1),
        elapsed_ms=round((now - started_at) * 1000, 1),
        request_id=getattr(state, "request_id", None),
        **fields,
    )
