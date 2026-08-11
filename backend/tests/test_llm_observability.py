from __future__ import annotations

from dataclasses import asdict

from app.core.observability.llm_trace import (
    ObservabilityContext,
    TraceContext,
    resolve_content_capture,
)
from app.core.observability.redaction import REDACTION_PII, redact_payload


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
    context = ObservabilityContext(
        TraceContext(trace_id="run-1", session_id="session-1", org_id="org-1"), sink
    )
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


def test_content_capture_disabled_drops_payload_after_redaction() -> None:
    sink = _Sink()
    context = ObservabilityContext(
        TraceContext(
            trace_id="run-2",
            session_id=None,
            org_id="org-1",
            content_capture=False,
        ),
        sink,
    )
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
    context = ObservabilityContext(
        TraceContext(trace_id="run-3", session_id=None, org_id="org-1"), sink
    )

    handle = context.start_generation(
        name="test",
        provider="test",
        model="test",
        input={"message": "safe"},
    )
    handle.finish_success(output="done")

    # The assertion is intentionally only that finish_success did not raise.
    assert asdict(handle._record)["status"] == "success"  # noqa: SLF001
