from __future__ import annotations

import time
from contextlib import nullcontext

import pytest

from app.config import Settings
from app.core.observability.langfuse_sink import LangfuseSink, build_langfuse_sink
from app.core.observability.llm_trace import GenerationRecord, ToolObservation, TraceContext


class _Observation:
    def __init__(self, observation_id: str) -> None:
        self.id = observation_id
        self.ended = False

    def end(self) -> None:
        self.ended = True


class _Client:
    def __init__(self, *, slow_flush: bool = False, failing_flush: bool = False) -> None:
        self.calls: list[dict] = []
        self.observations: list[_Observation] = []
        self.slow_flush = slow_flush
        self.failing_flush = failing_flush

    def start_observation(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        observation = _Observation(f"{len(self.observations) + 1:016x}")
        self.observations.append(observation)
        return observation

    def flush(self) -> None:
        if self.slow_flush:
            time.sleep(0.2)
        if self.failing_flush:
            raise RuntimeError("unavailable")


@pytest.fixture(autouse=True)
def _fake_attributes(monkeypatch):
    import langfuse

    monkeypatch.setattr(langfuse, "propagate_attributes", lambda **_: nullcontext())


def _context() -> TraceContext:
    return TraceContext(
        trace_id="0123456789abcdef0123456789abcdef",
        session_id="session-1",
        org_id="org-1",
        user_id="user-1",
    )


def test_emit_generation_maps_trace_parent_model_usage_and_status() -> None:
    client = _Client()
    sink = LangfuseSink("pk", "sk", client=client)
    sink._observation_ids["parent-1"] = "0123456789abcdef"  # noqa: SLF001
    record = GenerationRecord(
        observation_id="observation-1",
        trace_id=_context().trace_id,
        parent_id="parent-1",
        name="final-response",
        provider="openai",
        model="gpt-test",
        input={"prompt": "safe"},
        output="done",
        input_tokens=2,
        output_tokens=3,
        total_tokens=5,
        cost_usd=0.01,
        status="error",
        error={"message": "provider failed"},
        retry_index=1,
        fallback_from="gpt-primary",
    )

    sink.emit_generation(_context(), record)

    call = client.calls[0]
    assert call["as_type"] == "generation"
    assert call["trace_context"] == {
        "trace_id": _context().trace_id,
        "parent_span_id": "0123456789abcdef",
    }
    assert call["model"] == "gpt-test"
    assert call["usage_details"] == {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}
    assert call["metadata"]["retry_index"] == 1
    assert call["metadata"]["fallback_from"] == "gpt-primary"
    assert call["level"] == "ERROR"
    assert client.observations[0].ended is True


def test_emit_tool_maps_arguments_result_and_status() -> None:
    client = _Client()
    sink = LangfuseSink("pk", "sk", client=client)
    record = ToolObservation(
        observation_id="tool-1",
        trace_id=_context().trace_id,
        parent_id=None,
        tool_name="search",
        tool_call_id="call-1",
        arguments={"query": "safe"},
        result={"items": 1},
        status="success",
        duration_ms=42,
    )

    sink.emit_tool(_context(), record)

    call = client.calls[0]
    assert call["as_type"] == "span"
    assert call["name"] == "search"
    assert call["input"] == {"query": "safe"}
    assert call["output"] == {"items": 1}
    assert call["metadata"]["tool_call_id"] == "call-1"
    assert call["metadata"]["duration_ms"] == 42


def test_flush_is_bounded_and_ignores_client_failure() -> None:
    sink = LangfuseSink("pk", "sk", client=_Client(slow_flush=True, failing_flush=True))

    started = time.monotonic()
    sink.flush(0.01)

    assert time.monotonic() - started < 0.1


@pytest.mark.parametrize("field", ["observability_enabled", "langfuse_enabled"])
def test_disabled_settings_do_not_construct_sink(field: str) -> None:
    values = {"observability_enabled": True, "langfuse_enabled": True, "langfuse_public_key": "pk", "langfuse_secret_key": "sk"}
    values[field] = False

    assert build_langfuse_sink(Settings(**values)) is None
