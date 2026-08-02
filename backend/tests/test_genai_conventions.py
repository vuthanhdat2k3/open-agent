"""M13 — OTel GenAI semantic-convention guards.

Two things are protected here:

1. The span tree and attribute names the runtime actually emits.
2. Convention drift: ``genai.py`` must keep sourcing names from
   ``opentelemetry.semconv`` rather than drifting to hand-written strings,
   so a semconv upgrade that renames an attribute fails loudly.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as semconv

from app.core.observability import genai


class _FakeAgent:
    id = "agent-1"
    name = "researcher"
    org_id = "org-1"
    active_release_id = "release-7"


class _FakeProvider:
    key = "OpenAI"
    name = "OpenAI"


@pytest.fixture
def exporter():
    """Install a fresh in-memory tracer for one test.

    ``genai.tracer`` is bound at import time, so it is repointed at the
    per-test provider rather than mutating global tracing state.
    """
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    original = genai.tracer
    genai.tracer = provider.get_tracer("test")
    try:
        yield exp
    finally:
        genai.tracer = original


def _by_name(exporter: InMemorySpanExporter) -> dict:
    return {s.name: s for s in exporter.get_finished_spans()}


# --------------------------------------------------------------------------- #
# Drift guard
# --------------------------------------------------------------------------- #
def test_attribute_names_come_from_semconv() -> None:
    """genai.py must not hand-roll attribute strings."""
    assert genai.OPERATION_NAME == semconv.GEN_AI_OPERATION_NAME
    assert genai.REQUEST_MODEL == semconv.GEN_AI_REQUEST_MODEL
    assert genai.USAGE_INPUT_TOKENS == semconv.GEN_AI_USAGE_INPUT_TOKENS
    assert genai.USAGE_OUTPUT_TOKENS == semconv.GEN_AI_USAGE_OUTPUT_TOKENS
    assert genai.TOOL_NAME == semconv.GEN_AI_TOOL_NAME
    assert genai.AGENT_ID == semconv.GEN_AI_AGENT_ID
    assert genai.CONVERSATION_ID == semconv.GEN_AI_CONVERSATION_ID

    assert semconv.GenAiOperationNameValues.CHAT.value == genai.OP_CHAT
    assert semconv.GenAiOperationNameValues.INVOKE_AGENT.value == genai.OP_INVOKE_AGENT
    assert semconv.GenAiOperationNameValues.EXECUTE_TOOL.value == genai.OP_EXECUTE_TOOL


def test_openagent_attributes_are_namespaced() -> None:
    """Non-standard attributes must not squat on the gen_ai.* namespace."""
    for attr in (
        genai.ORG_ID,
        genai.AGENT_RELEASE_ID,
        genai.RISK_TIER,
        genai.DEPTH,
        genai.WORKFLOW_RUN_ID,
        genai.USAGE_ESTIMATED,
    ):
        assert attr.startswith("openagent."), attr


# --------------------------------------------------------------------------- #
# Span shape
# --------------------------------------------------------------------------- #
def test_agent_span_carries_tenant_and_release(exporter: InMemorySpanExporter) -> None:
    with genai.agent_span(_FakeAgent(), session_id="sess-9", depth=2):
        pass

    attrs = _by_name(exporter)["invoke_agent researcher"].attributes
    assert attrs[genai.OPERATION_NAME] == "invoke_agent"
    assert attrs[genai.AGENT_ID] == "agent-1"
    assert attrs[genai.CONVERSATION_ID] == "sess-9"
    assert attrs[genai.ORG_ID] == "org-1"
    assert attrs[genai.AGENT_RELEASE_ID] == "release-7"
    assert attrs[genai.DEPTH] == 2


def test_llm_span_records_model_and_real_token_usage(exporter: InMemorySpanExporter) -> None:
    agent = _FakeAgent()
    with genai.llm_span(
        agent, provider=_FakeProvider(), model_name="gpt-4o-mini", temperature=0.3
    ) as span:
        genai.record_usage(
            span,
            {"input_tokens": 120, "output_tokens": 45},
            org_id=agent.org_id,
            model_name="gpt-4o-mini",
        )
        genai.record_finish_reasons(span, ["stop"])

    attrs = _by_name(exporter)["chat gpt-4o-mini"].attributes
    assert attrs[genai.OPERATION_NAME] == "chat"
    assert attrs[genai.REQUEST_MODEL] == "gpt-4o-mini"
    assert attrs[genai.SYSTEM] == "openai"
    assert attrs[genai.REQUEST_TEMPERATURE] == 0.3
    # Real counts, not zeros — the whole point of include_usage.
    assert attrs[genai.USAGE_INPUT_TOKENS] == 120
    assert attrs[genai.USAGE_OUTPUT_TOKENS] == 45
    assert attrs[genai.RESPONSE_FINISH_REASONS] == ("stop",)
    assert genai.USAGE_ESTIMATED not in attrs


def test_estimated_usage_is_flagged(exporter: InMemorySpanExporter) -> None:
    """A guess must never look like a measurement."""
    agent = _FakeAgent()
    with genai.llm_span(agent, provider=_FakeProvider(), model_name="local-model") as span:
        genai.record_usage(
            span,
            {"input_tokens": 10, "output_tokens": 5},
            org_id=agent.org_id,
            model_name="local-model",
            estimated=True,
        )

    attrs = _by_name(exporter)["chat local-model"].attributes
    assert attrs[genai.USAGE_ESTIMATED] is True


def test_tool_span_shape(exporter: InMemorySpanExporter) -> None:
    with genai.tool_span(
        _FakeAgent(), tool_name="web_fetch", risk_tier="network", call_id="call-3"
    ):
        pass

    attrs = _by_name(exporter)["execute_tool web_fetch"].attributes
    assert attrs[genai.OPERATION_NAME] == "execute_tool"
    assert attrs[genai.TOOL_NAME] == "web_fetch"
    assert attrs[genai.TOOL_CALL_ID] == "call-3"
    assert attrs[genai.RISK_TIER] == "network"


def test_span_tree_agent_is_parent_of_chat_and_tool(exporter: InMemorySpanExporter) -> None:
    """invoke_agent -> {chat, execute_tool} must be one tree, not siblings.

    A flat span list makes a trace viewer useless for debugging a turn.
    """
    agent = _FakeAgent()
    with genai.agent_span(agent, session_id="sess-1"):
        with genai.llm_span(agent, provider=_FakeProvider(), model_name="gpt-4o-mini"):
            pass
        with genai.tool_span(agent, tool_name="rag_search", risk_tier="read"):
            pass

    spans = _by_name(exporter)
    parent = spans["invoke_agent researcher"]
    chat = spans["chat gpt-4o-mini"]
    tool = spans["execute_tool rag_search"]

    parent_span_id = parent.context.span_id
    assert chat.parent is not None and chat.parent.span_id == parent_span_id
    assert tool.parent is not None and tool.parent.span_id == parent_span_id
    assert chat.context.trace_id == parent.context.trace_id == tool.context.trace_id


def test_workflow_node_span_maps_node_type_to_operation(exporter: InMemorySpanExporter) -> None:
    for node_type, expected_op in (
        ("agent", "invoke_agent"),
        ("tool", "execute_tool"),
        ("merge", "invoke_workflow"),
    ):
        with genai.workflow_node_span(
            org_id="org-1",
            workflow_run_id="run-1",
            node_id=f"node-{node_type}",
            node_type=node_type,
            workflow_name="research-pipeline",
        ):
            pass

        attrs = _by_name(exporter)[f"{expected_op} node-{node_type}"].attributes
        assert attrs[genai.OPERATION_NAME] == expected_op
        assert attrs[genai.WORKFLOW_RUN_ID] == "run-1"
        assert attrs[genai.ORG_ID] == "org-1"


def test_message_content_capture_is_off_by_default() -> None:
    """Prompt/completion bodies carry PII and secrets — opt-in only."""
    assert genai.capture_message_content() is False