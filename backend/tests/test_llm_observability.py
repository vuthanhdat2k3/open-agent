from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

import pytest

from app.core.observability.driver import ObservableLLMDriver
from app.core.observability.llm_trace import (
    ObservabilityContext,
    TraceContext,
    _is_sampled,
    resolve_content_capture,
)
from app.core.observability.redaction import (
    REDACTION_PII,
    redact_payload,
    truncate_payload,
)
from app.core.providers.driver import ModelInfo
from app.core.providers.driver import TestResult as DriverTestResult


class _Sink:
    def __init__(self, *, raises: bool = False) -> None:
        self.generations = []
        self.tools = []
        self.raises = raises

    def emit_generation(self, context, record) -> None:  # noqa: ANN001
        if self.raises:
            raise RuntimeError("sink unavailable")
        self.generations.append(record)

    def emit_tool(self, context, record) -> None:  # noqa: ANN001
        if self.raises:
            raise RuntimeError("sink unavailable")
        self.tools.append(record)

    def flush(self, timeout_seconds: float = 5.0) -> None:
        return None


class _FakeDriver:
    supports_tools = True
    supports_reasoning = True
    supports_vision = False

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def test_connection(self) -> DriverTestResult:
        return DriverTestResult(ok=True, latency_ms=1, message="ok")

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
    ) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
        if self.fail:
            raise RuntimeError("provider secret=abcdefghijklmnopqrstuvwxyz")
        return "done", {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}, []

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "content", "text": "hello "}
        if self.fail:
            raise RuntimeError("Bearer secret-abcdefghijklmnopqrstuvwxyz")
        yield {"type": "reasoning", "text": "reason"}
        yield {
            "type": "tool_calls",
            "tool_calls": [{"id": "call-1", "name": "search", "arguments": "{}"}],
        }
        yield {
            "type": "usage",
            "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        }


def _context(sink: _Sink, *, capture: bool = True) -> ObservabilityContext:
    return ObservabilityContext(
        TraceContext(
            trace_id="run-1",
            session_id="session-1",
            org_id="org-1",
            content_capture=capture,
        ),
        sink,
    )


def test_truncate_payload_is_explicit_and_does_not_mutate_source() -> None:
    raw = {"content": "x" * 256}

    safe, truncated = truncate_payload(raw, 48)

    assert truncated is True
    assert raw["content"] == "x" * 256
    assert safe["_truncated"] is True
    assert safe["preview"].endswith("[TRUNCATED]")


def test_redaction_deep_copies_and_masks_secrets_and_pii() -> None:
    raw = {
        "prompt": "Contact alice@example.com or +84 912 345 678",
        "credentials": {"api_key": "super-secret-value"},
        "nested": [{"authorization": "Bearer abc"}],
    }

    safe, stats = redact_payload(raw)

    assert raw["credentials"]["api_key"] == "super-secret-value"
    assert safe["credentials"]["api_key"] == "[REDACTED_SECRET]"
    assert safe["prompt"].count(REDACTION_PII) == 2
    assert safe["nested"][0]["authorization"] == "[REDACTED_SECRET]"
    assert stats.count >= 4
    assert "alice@example.com" not in str(safe)


def test_observation_finish_is_idempotent_and_redacts_record() -> None:
    sink = _Sink()
    context = _context(sink)
    handle = context.start_generation(
        name="final-response",
        provider="openai",
        model="gpt-test",
        input=[{"role": "user", "content": "email alice@example.com"}],
    )

    handle.finish_success(output="token=abcdefghijklmnopqrstuvwx", usage={"input_tokens": 2})
    handle.finish_error(RuntimeError("should not replace success"))
    handle.finish_cancelled()

    assert len(sink.generations) == 1
    record = sink.generations[0]
    assert record.status == "success"
    assert "alice@example.com" not in str(record.input)
    assert "abcdefghijklmnopqrstuvwx" not in str(record.output)
    assert record.metadata["redaction_applied"] is True


def test_content_capture_policy_cannot_be_widened_by_lower_levels() -> None:
    assert resolve_content_capture(True) is True
    assert resolve_content_capture(True, org_allowed=False, request_allowed=True) is False
    assert resolve_content_capture(False, org_allowed=True, agent_allowed=True, request_allowed=True) is False
    assert resolve_content_capture(True, org_allowed=True, agent_allowed=True, request_allowed=False) is False


def test_sampling_is_deterministic_and_honors_boundaries() -> None:
    assert _is_sampled("run-1", 0.0) is False
    assert _is_sampled("run-1", 1.0) is True
    assert _is_sampled("run-1", 0.37) == _is_sampled("run-1", 0.37)


def test_content_capture_disabled_drops_payload_after_redaction() -> None:
    sink = _Sink()
    context = _context(sink, capture=False)
    handle = context.start_tool_observation(
        tool_name="search",
        tool_call_id="call-1",
        arguments={"query": "private@example.com"},
    )
    handle.finish_success(result="private@example.com")

    assert len(sink.tools) == 1
    record = sink.tools[0]
    assert record.arguments is None
    assert record.result is None
    assert record.metadata["content_capture"] is False


def test_sink_failure_never_escapes_observation_lifecycle() -> None:
    sink = _Sink(raises=True)
    handle = _context(sink).start_generation(
        name="test",
        provider="test",
        model="test",
        input={"message": "safe"},
    )
    handle.finish_success(output="done")

    assert asdict(handle._record)["status"] == "success"  # noqa: SLF001


@pytest.mark.asyncio
async def test_observable_driver_records_one_complete_generation() -> None:
    sink = _Sink()
    driver = ObservableLLMDriver(
        _FakeDriver(), _context(sink), provider="openai", model="gpt-test"
    )

    result = await driver.complete([{"role": "user", "content": "alice@example.com"}])

    assert result[0] == "done"
    assert len(sink.generations) == 1
    record = sink.generations[0]
    assert record.status == "success"
    assert record.input_tokens == 2
    assert record.output_tokens == 3
    assert record.total_tokens == 5
    assert "alice@example.com" not in str(record.input)
    assert driver.last_observation_id == record.observation_id


@pytest.mark.asyncio
async def test_observable_driver_records_one_stream_generation() -> None:
    sink = _Sink()
    driver = ObservableLLMDriver(
        _FakeDriver(), _context(sink), provider="gemini", model="gemini-test"
    )

    events = [event async for event in driver.stream([{"role": "user", "content": "hi"}])]

    assert len(events) == 4
    assert len(sink.generations) == 1
    record = sink.generations[0]
    assert record.status == "success"
    assert record.output == {"content": "hello ", "reasoning": "reason"}
    assert record.tool_calls[0]["name"] == "search"
    assert driver.last_observation_id == record.observation_id


@pytest.mark.asyncio
async def test_observable_driver_closes_early_stream_as_cancelled() -> None:
    sink = _Sink()
    driver = ObservableLLMDriver(
        _FakeDriver(), _context(sink), provider="openai", model="gpt-test"
    )

    stream = driver.stream([{"role": "user", "content": "hi"}])
    assert (await anext(stream))["type"] == "content"
    await stream.aclose()

    assert len(sink.generations) == 1
    assert sink.generations[0].status == "cancelled"


@pytest.mark.asyncio
async def test_observable_driver_records_provider_error_without_swallowing_it() -> None:
    sink = _Sink()
    driver = ObservableLLMDriver(
        _FakeDriver(fail=True), _context(sink), provider="anthropic", model="claude-test"
    )

    with pytest.raises(RuntimeError, match="provider secret"):
        await driver.complete([{"role": "user", "content": "hi"}])

    assert len(sink.generations) == 1
    record = sink.generations[0]
    assert record.status == "error"
    assert "abcdefghijklmnopqrstuvwxyz" not in str(record.error)
