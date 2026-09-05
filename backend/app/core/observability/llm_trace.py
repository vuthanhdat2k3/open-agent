"""Provider-neutral LLM observability contracts and lifecycle helpers.

Business logic depends on this module, never on a concrete observability
backend. A sink receives only sanitized records after they are finalized.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

from app.config import get_settings
from app.core.observability.metrics import (
    llm_observability_events_total,
    llm_observability_export_failures_total,
    llm_observability_redactions_total,
)
from app.core.observability.redaction import RedactionStats, redact_payload, truncate_payload
from app.db.base import utc_now

logger = logging.getLogger(__name__)
_export_failure_log_at: dict[str, float] = {}
_EXPORT_FAILURE_LOG_INTERVAL_SECONDS = 60.0

ObservationKind = Literal["span", "generation", "event"]
GenerationStatus = Literal["started", "success", "error", "cancelled"]
ToolStatus = Literal["started", "success", "error", "denied", "cancelled"]


@dataclass(frozen=True)
class TraceContext:
    """Stable trace identity and resolved content policy for one run."""

    trace_id: str
    session_id: str | None
    org_id: str
    user_id: str | None = None
    agent_id: str | None = None
    agent_release_id: str | None = None
    parent_observation_id: str | None = None
    content_capture: bool = True
    sampling_rate: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def child(self, parent_observation_id: str | None) -> TraceContext:
        """Return a context with a different parent, preserving trace identity."""
        return replace(self, parent_observation_id=parent_observation_id)


@dataclass
class GenerationRecord:
    """Backend-independent representation of one complete LLM attempt."""

    observation_id: str
    trace_id: str
    parent_id: str | None
    name: str
    provider: str
    model: str
    input: Any
    output: Any | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    estimated: bool | None = None
    latency_ms: int = 0
    status: GenerationStatus = "started"
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retry_index: int = 0
    fallback_from: str | None = None
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None


@dataclass
class ToolObservation:
    """Backend-independent representation of one tool execution."""

    observation_id: str
    trace_id: str
    parent_id: str | None
    tool_name: str
    tool_call_id: str | None
    arguments: Any
    result: Any | None = None
    status: ToolStatus = "started"
    duration_ms: int | None = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None


class ObservationHandle(Protocol):
    """Lifecycle API shared by generation and tool observations."""

    observation_id: str
    trace_id: str
    parent_id: str | None
    kind: ObservationKind

    def finish_success(self, **fields: Any) -> None: ...

    def finish_error(self, exc: BaseException, **fields: Any) -> None: ...

    def finish_cancelled(self, **fields: Any) -> None: ...


class ObservabilitySink(Protocol):
    """Backend adapter contract; implementations receive sanitized records."""

    def emit_generation(self, context: TraceContext, record: GenerationRecord) -> None: ...

    def emit_tool(self, context: TraceContext, record: ToolObservation) -> None: ...

    def flush(self, timeout_seconds: float = 5.0) -> None: ...


class NoopSink:
    """Safe default sink used when observability is disabled or unconfigured."""

    def emit_generation(self, context: TraceContext, record: GenerationRecord) -> None:
        return None

    def emit_tool(self, context: TraceContext, record: ToolObservation) -> None:
        return None

    def flush(self, timeout_seconds: float = 5.0) -> None:
        return None



_default_sink: ObservabilitySink = NoopSink()


def set_default_sink(sink: ObservabilitySink) -> None:
    global _default_sink
    _default_sink = sink


def get_default_sink() -> ObservabilitySink:
    return _default_sink

class _LifecycleHandle:
    def __init__(
        self,
        *,
        context: TraceContext,
        kind: ObservationKind,
        record: GenerationRecord | ToolObservation,
        emit,
    ) -> None:
        self._context = context
        self.kind = kind
        self._record = record
        self._emit = emit
        self._started_monotonic = time.monotonic()
        self._finished = False

    @property
    def observation_id(self) -> str:
        return self._record.observation_id

    @property
    def trace_id(self) -> str:
        return self._record.trace_id

    @property
    def parent_id(self) -> str | None:
        return self._record.parent_id

    def finish_success(self, **fields: Any) -> None:
        self._finish("success", fields=fields)

    def finish_error(self, exc: BaseException, **fields: Any) -> None:
        fields = {**fields, "error": {"type": type(exc).__name__, "message": str(exc)}}
        self._finish("error", fields=fields)

    def finish_cancelled(self, **fields: Any) -> None:
        self._finish("cancelled", fields=fields)

    def _finish(self, status: str, *, fields: dict[str, Any]) -> None:
        if self._finished:
            return
        self._finished = True
        ended_at = utc_now()
        latency_ms = max(0, int((time.monotonic() - self._started_monotonic) * 1000))
        fields = {**fields, "status": status, "ended_at": ended_at}
        if isinstance(self._record, GenerationRecord):
            usage = fields.pop("usage", None)
            if isinstance(usage, dict):
                fields.setdefault("input_tokens", usage.get("input_tokens"))
                fields.setdefault("output_tokens", usage.get("output_tokens"))
                fields.setdefault("total_tokens", usage.get("total_tokens"))
            fields.setdefault("latency_ms", latency_ms)
        else:
            fields.setdefault("duration_ms", latency_ms)
        for key, value in fields.items():
            if hasattr(self._record, key):
                setattr(self._record, key, value)
        self._emit(self._context, self._record, self.kind)


class ObservabilityContext:
    """Creates observations and sanitizes them before sending to a sink."""

    def __init__(self, trace: TraceContext, sink: ObservabilitySink | None = None) -> None:
        self.trace = trace
        self.sink = sink or get_default_sink()

    def child(self, parent_observation_id: str | None) -> ObservabilityContext:
        return ObservabilityContext(self.trace.child(parent_observation_id), self.sink)

    def start_generation(
        self,
        *,
        name: str,
        provider: str,
        model: str,
        input: Any,
        metadata: dict[str, Any] | None = None,
        retry_index: int = 0,
        fallback_from: str | None = None,
        parent_id: str | None = None,
    ) -> ObservationHandle:
        record = GenerationRecord(
            observation_id=str(uuid4()),
            trace_id=self.trace.trace_id,
            parent_id=parent_id or self.trace.parent_observation_id,
            name=name,
            provider=provider,
            model=model,
            input=input,
            metadata=dict(metadata or {}),
            retry_index=retry_index,
            fallback_from=fallback_from,
        )
        return _LifecycleHandle(
            context=self.trace,
            kind="generation",
            record=record,
            emit=self._emit,
        )

    def start_tool_observation(
        self,
        *,
        tool_name: str,
        tool_call_id: str | None,
        arguments: Any,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> ObservationHandle:
        record = ToolObservation(
            observation_id=str(uuid4()),
            trace_id=self.trace.trace_id,
            parent_id=parent_id or self.trace.parent_observation_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=arguments,
            metadata=dict(metadata or {}),
        )
        return _LifecycleHandle(
            context=self.trace,
            kind="span",
            record=record,
            emit=self._emit,
        )

    def _emit(
        self,
        context: TraceContext,
        record: GenerationRecord | ToolObservation,
        kind: ObservationKind,
    ) -> None:
        try:
            safe_record, stats = _sanitize_record(context, record)
        except Exception:  # noqa: BLE001
            # Never send raw content after a sanitizer failure.
            safe_record = _safe_contentless_record(record)
            stats = RedactionStats(failed=True)
        metadata = getattr(safe_record, "metadata", {})
        metadata.update(stats.as_metadata(content_capture=context.content_capture))
        safe_record.metadata = metadata
        if stats.count:
            llm_observability_redactions_total.labels(kind).inc(stats.count)
        llm_observability_events_total.labels(kind).inc()
        try:
            if kind == "generation":
                self.sink.emit_generation(context, safe_record)
            else:
                self.sink.emit_tool(context, safe_record)
        except Exception as exc:  # noqa: BLE001
            sink_name = type(self.sink).__name__
            llm_observability_export_failures_total.labels(sink_name).inc()
            now = time.monotonic()
            if now - _export_failure_log_at.get(sink_name, 0.0) >= _EXPORT_FAILURE_LOG_INTERVAL_SECONDS:
                _export_failure_log_at[sink_name] = now
                logger.warning(
                    "LLM observability export failed",
                    extra={"sink": sink_name, "error_type": type(exc).__name__},
                )


def _bound_sanitized_content(
    fields: dict[str, Any], stats: RedactionStats
) -> dict[str, Any]:
    """Bound all content persisted by sinks after it has already been redacted."""
    bounded, truncated = truncate_payload(
        fields, max(0, get_settings().observability_max_content_bytes)
    )
    if not truncated:
        return fields
    stats.content_truncated = True
    if "input" in fields:
        return {
            "input": bounded,
            "output": None,
            "error": None,
            "metadata": {},
            "tool_calls": [],
        }
    return {"arguments": bounded, "result": None, "error": None, "metadata": {}}


def _sanitize_record(
    context: TraceContext, record: GenerationRecord | ToolObservation
) -> tuple[GenerationRecord | ToolObservation, RedactionStats]:
    if isinstance(record, GenerationRecord):
        fields = {
            "input": record.input,
            "output": record.output,
            "error": record.error,
            "metadata": record.metadata,
            "tool_calls": record.tool_calls,
        }
        safe, stats = redact_payload(fields)
        if not context.content_capture:
            safe["input"] = None
            safe["output"] = None
            safe["tool_calls"] = []
        safe = _bound_sanitized_content(safe, stats)
        return replace(
            record,
            input=safe["input"],
            output=safe["output"],
            error=safe["error"],
            metadata=safe["metadata"],
            tool_calls=safe["tool_calls"],
        ), stats
    fields = {
        "arguments": record.arguments,
        "result": record.result,
        "error": record.error,
        "metadata": record.metadata,
    }
    safe, stats = redact_payload(fields)
    if not context.content_capture:
        safe["arguments"] = None
        safe["result"] = None
    safe = _bound_sanitized_content(safe, stats)
    return replace(
        record,
        arguments=safe["arguments"],
        result=safe["result"],
        error=safe["error"],
        metadata=safe["metadata"],
    ), stats


def _safe_contentless_record(record: GenerationRecord | ToolObservation):
    if isinstance(record, GenerationRecord):
        return replace(record, input=None, output=None, tool_calls=[], error=None)
    return replace(record, arguments=None, result=None, error=None)


def _is_sampled(trace_id: str, sampling_rate: float) -> bool:
    """Deterministically sample by trace id so retries/reconnects agree."""
    rate = max(0.0, min(1.0, sampling_rate))
    if rate == 0.0:
        return False
    if rate == 1.0:
        return True
    bucket = int.from_bytes(hashlib.sha256(trace_id.encode("utf-8")).digest()[:8], "big")
    return bucket / (2**64 - 1) < rate


def resolve_content_capture(
    global_allowed: bool,
    *,
    org_allowed: bool | None = None,
    agent_allowed: bool | None = None,
    request_allowed: bool | None = None,
) -> bool:
    """Apply global → org → agent → request policy without widening access."""
    allowed = bool(global_allowed)
    for override in (org_allowed, agent_allowed, request_allowed):
        if override is False:
            allowed = False
    return allowed


def build_trace_context(
    *,
    trace_id: str,
    session_id: str | None,
    org_id: str,
    user_id: str | None = None,
    agent_id: str | None = None,
    agent_release_id: str | None = None,
    parent_observation_id: str | None = None,
    org_allowed: bool | None = None,
    agent_allowed: bool | None = None,
    request_allowed: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> TraceContext:
    settings = get_settings()
    sampling_rate = max(0.0, min(1.0, settings.observability_sampling_rate))
    policy_allows_content = resolve_content_capture(
        settings.observability_capture_content,
        org_allowed=org_allowed,
        agent_allowed=agent_allowed,
        request_allowed=request_allowed,
    )
    return TraceContext(
        trace_id=trace_id,
        session_id=session_id,
        org_id=org_id,
        user_id=user_id,
        agent_id=agent_id,
        agent_release_id=agent_release_id,
        parent_observation_id=parent_observation_id,
        content_capture=policy_allows_content and _is_sampled(trace_id, sampling_rate),
        sampling_rate=sampling_rate,
        metadata=dict(metadata or {}),
    )
