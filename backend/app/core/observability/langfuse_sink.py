"""Langfuse v4 adapter for the provider-neutral observability contract."""

from __future__ import annotations

import hashlib
import re
import threading
from contextlib import nullcontext
from typing import Any

from app.core.observability.llm_trace import GenerationRecord, ToolObservation, TraceContext

_VALID_LANGFUSE_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


def langfuse_trace_id(trace_id: str) -> str:
    """Map any internal trace id to a valid 32 lowercase hex Langfuse trace id.

    ``root_run_id`` is the internal trace identity and must stay exactly as
    generated everywhere else in OpenAgent (Task.id, debug links, audit
    logs). Some call sites (the chat UI) still produce dash-formatted UUIDv4
    values. Rather than changing that internal id, this hashes any
    non-conforming id deterministically so the same ``root_run_id`` always
    maps to the same Langfuse trace id across retries/reconnects, and valid
    32-hex ids (already the common case) pass through untouched.
    """
    if _VALID_LANGFUSE_TRACE_ID.match(trace_id):
        return trace_id
    return hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:32]


class LangfuseSink:
    def __init__(self, public_key: str, secret_key: str, base_url: str = "", client: Any = None):
        if client is None:
            from langfuse import Langfuse

            kwargs = {"public_key": public_key, "secret_key": secret_key}
            if base_url:
                kwargs["base_url"] = base_url
            client = Langfuse(**kwargs)
        self.client = client
        self._observation_ids: dict[str, str] = {}
        self._lock = threading.Lock()

    def _attributes(self, context: TraceContext):
        try:
            from langfuse import propagate_attributes

            return propagate_attributes(
                user_id=context.user_id,
                session_id=context.session_id,
                metadata={**context.metadata, "org_id": context.org_id},
                tags=[value for value in (context.org_id, context.agent_id) if value],
            )
        except ImportError:
            return nullcontext()

    def _trace_context(self, context: TraceContext, parent_id: str | None) -> dict[str, str]:
        trace_context = {"trace_id": langfuse_trace_id(context.trace_id)}
        if parent_id:
            with self._lock:
                trace_context["parent_span_id"] = self._observation_ids.get(parent_id, parent_id)
        return trace_context

    def emit_generation(self, context: TraceContext, record: GenerationRecord) -> None:
        metadata = {
            **record.metadata,
            "provider": record.provider,
            "retry_index": record.retry_index,
            "latency_ms": record.latency_ms,
        }
        if record.error:
            metadata["error"] = record.error
        if record.fallback_from:
            metadata["fallback_from"] = record.fallback_from
        if record.estimated is not None:
            # Langfuse has no native "is this a guess" field - surface it in
            # metadata so a real vs. provider-estimated token/cost figure
            # isn't presented as an authoritative measurement.
            metadata["usage_estimated"] = record.estimated
        usage = {
            key: value
            for key, value in {
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "total_tokens": record.total_tokens,
            }.items()
            if value is not None
        }
        kwargs: dict[str, Any] = {
            "trace_context": self._trace_context(context, record.parent_id),
            "name": record.name,
            "as_type": "generation",
            "model": record.model,
            "input": record.input,
            "output": record.output,
            "metadata": metadata,
            "usage_details": usage or None,
            "status_message": _status_message(record.status, record.error),
        }
        if record.status == "error":
            kwargs["level"] = "ERROR"
        if record.cost_usd is not None:
            kwargs["cost_details"] = {"total_cost": record.cost_usd}
        with self._attributes(context):
            observation = self.client.start_observation(**kwargs)
            self._remember_observation(record.observation_id, observation)
            observation.end()

    def emit_tool(self, context: TraceContext, record: ToolObservation) -> None:
        metadata = {
            **record.metadata,
            "tool_name": record.tool_name,
            "tool_call_id": record.tool_call_id,
            "duration_ms": record.duration_ms,
        }
        if record.error:
            metadata["error"] = record.error
        kwargs = {
            "trace_context": self._trace_context(context, record.parent_id),
            "name": record.tool_name,
            "as_type": "span",
            "input": record.arguments,
            "output": record.result,
            "metadata": metadata,
            "status_message": _status_message(record.status, record.error),
        }
        if record.status in {"error", "denied"}:
            kwargs["level"] = "ERROR"
        with self._attributes(context):
            observation = self.client.start_observation(**kwargs)
            self._remember_observation(record.observation_id, observation)
            observation.end()

    def _remember_observation(self, internal_id: str, observation: Any) -> None:
        observation_id = getattr(observation, "id", None)
        if observation_id:
            with self._lock:
                self._observation_ids[internal_id] = observation_id

    def flush(self, timeout_seconds: float = 5.0) -> None:
        error: list[BaseException] = []

        def _flush() -> None:
            try:
                self.client.flush()
            except BaseException as exc:  # SDK cleanup must not break shutdown.
                error.append(exc)

        thread = threading.Thread(target=_flush, daemon=True)
        thread.start()
        thread.join(max(0.0, timeout_seconds))


def _status_message(status: str, error: dict[str, Any] | None) -> str | None:
    if status in {"success", "started"}:
        return None
    return (error or {}).get("message") or status


def build_langfuse_sink(settings: Any) -> LangfuseSink | None:
    if not (
        settings.observability_enabled
        and settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    ):
        return None
    return LangfuseSink(
        settings.langfuse_public_key,
        settings.langfuse_secret_key,
        settings.langfuse_base_url,
    )
