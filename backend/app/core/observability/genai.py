"""OpenTelemetry GenAI semantic-convention helpers.

This module is the **single place** that knows GenAI attribute names. Every
other module goes through the helpers here, so a convention change (the
GenAI semconv is still incubating) is a one-file edit rather than a grep
across the runtime.

Attribute names come from ``opentelemetry.semconv`` constants rather than
string literals, so bumping the semconv package surfaces renames as import
errors instead of silently emitting stale attributes. See
``tests/test_genai_conventions.py`` for the drift guard.

Attributes that are *not* part of the standard (tenant, release, risk tier)
are namespaced under ``openagent.*`` so they never collide with future
standard names.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as _g
from opentelemetry.trace import Span

from app.config import get_settings
from app.core.observability.metrics import (
    gen_ai_client_token_usage,
    gen_ai_operation_duration_seconds,
)
from app.core.observability.tracing import get_tracer

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

settings = get_settings()
tracer = get_tracer(__name__)

# --------------------------------------------------------------------------- #
# Standard attribute names (re-exported so callers never hardcode strings)
# --------------------------------------------------------------------------- #
OPERATION_NAME = _g.GEN_AI_OPERATION_NAME
SYSTEM = _g.GEN_AI_SYSTEM
REQUEST_MODEL = _g.GEN_AI_REQUEST_MODEL
RESPONSE_MODEL = _g.GEN_AI_RESPONSE_MODEL
REQUEST_TEMPERATURE = _g.GEN_AI_REQUEST_TEMPERATURE
USAGE_INPUT_TOKENS = _g.GEN_AI_USAGE_INPUT_TOKENS
USAGE_OUTPUT_TOKENS = _g.GEN_AI_USAGE_OUTPUT_TOKENS
RESPONSE_FINISH_REASONS = _g.GEN_AI_RESPONSE_FINISH_REASONS
TOOL_NAME = _g.GEN_AI_TOOL_NAME
TOOL_CALL_ID = _g.GEN_AI_TOOL_CALL_ID
TOOL_DESCRIPTION = _g.GEN_AI_TOOL_DESCRIPTION
AGENT_ID = _g.GEN_AI_AGENT_ID
AGENT_NAME = _g.GEN_AI_AGENT_NAME
CONVERSATION_ID = _g.GEN_AI_CONVERSATION_ID
TOKEN_TYPE = _g.GEN_AI_TOKEN_TYPE
WORKFLOW_NAME = _g.GEN_AI_WORKFLOW_NAME

OP_CHAT = _g.GenAiOperationNameValues.CHAT.value
OP_INVOKE_AGENT = _g.GenAiOperationNameValues.INVOKE_AGENT.value
OP_EXECUTE_TOOL = _g.GenAiOperationNameValues.EXECUTE_TOOL.value
OP_INVOKE_WORKFLOW = _g.GenAiOperationNameValues.INVOKE_WORKFLOW.value

TOKEN_TYPE_INPUT = _g.GenAiTokenTypeValues.INPUT.value
TOKEN_TYPE_OUTPUT = _g.GenAiTokenTypeValues.OUTPUT.value

# --------------------------------------------------------------------------- #
# OpenAgent-specific attributes (deliberately namespaced, not standard)
# --------------------------------------------------------------------------- #
ORG_ID = "openagent.org_id"
AGENT_RELEASE_ID = "openagent.agent_release_id"
RISK_TIER = "openagent.risk_tier"
DEPTH = "openagent.depth"
WORKFLOW_RUN_ID = "openagent.workflow_run_id"
NODE_ID = "openagent.node_id"
NODE_TYPE = "openagent.node_type"
USAGE_ESTIMATED = "openagent.usage_estimated"
TOOL_STATUS = "openagent.tool_status"


def _clean(attrs: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values — OTel rejects them and they add no signal."""
    return {k: v for k, v in attrs.items() if v is not None}


def common_attributes(agent: Any, *, session_id: str | None = None) -> dict[str, Any]:
    """Tenant/agent/release attributes that belong on every runtime span."""
    return _clean(
        {
            AGENT_ID: getattr(agent, "id", None),
            AGENT_NAME: getattr(agent, "name", None),
            CONVERSATION_ID: session_id,
            ORG_ID: getattr(agent, "org_id", None),
            AGENT_RELEASE_ID: getattr(agent, "active_release_id", None),
        }
    )


@contextmanager
def agent_span(agent: Any, *, session_id: str | None = None, depth: int = 0) -> Iterator[Span]:
    """Span for one agent-loop iteration (``invoke_agent``)."""
    attrs = common_attributes(agent, session_id=session_id)
    attrs[OPERATION_NAME] = OP_INVOKE_AGENT
    attrs[DEPTH] = depth
    name = f"{OP_INVOKE_AGENT} {getattr(agent, 'name', 'agent')}"
    with tracer.start_as_current_span(name, attributes=attrs) as span:
        yield span


@contextmanager
def llm_span(
    agent: Any,
    *,
    provider: Any,
    model_name: str,
    temperature: float | None = None,
    session_id: str | None = None,
) -> Iterator[Span]:
    """Span for a single LLM call (``chat``).

    M7 had no span carrying the model or token usage — this is where
    ``gen_ai.request.model`` and ``gen_ai.usage.*`` live.
    """
    attrs = common_attributes(agent, session_id=session_id)
    attrs[OPERATION_NAME] = OP_CHAT
    attrs[REQUEST_MODEL] = model_name
    system = getattr(provider, "key", None) or getattr(provider, "name", None)
    if system:
        attrs[SYSTEM] = str(system).lower()
    if temperature is not None:
        attrs[REQUEST_TEMPERATURE] = temperature

    org_id = getattr(agent, "org_id", "") or ""
    with (
        tracer.start_as_current_span(f"{OP_CHAT} {model_name}", attributes=attrs) as span,
        gen_ai_operation_duration_seconds.labels(org_id, OP_CHAT, model_name).time(),
    ):
        yield span


@contextmanager
def tool_span(
    agent: Any,
    *,
    tool_name: str,
    risk_tier: str | None = None,
    call_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[Span]:
    """Span for a single tool execution (``execute_tool``)."""
    attrs = common_attributes(agent, session_id=session_id)
    attrs[OPERATION_NAME] = OP_EXECUTE_TOOL
    attrs[TOOL_NAME] = tool_name
    if call_id:
        attrs[TOOL_CALL_ID] = call_id
    if risk_tier:
        attrs[RISK_TIER] = risk_tier
    with tracer.start_as_current_span(f"{OP_EXECUTE_TOOL} {tool_name}", attributes=attrs) as span:
        yield span


@contextmanager
def workflow_node_span(
    *,
    org_id: str,
    workflow_run_id: str,
    node_id: str,
    node_type: str,
    workflow_name: str | None = None,
    agent_release_id: str | None = None,
) -> Iterator[Span]:
    """Span for one workflow node run.

    Node type decides the operation: an ``agent`` node is an ``invoke_agent``,
    a ``tool`` node is an ``execute_tool``; anything structural (input/merge/
    output) is part of the workflow itself.
    """
    operation = {
        "agent": OP_INVOKE_AGENT,
        "tool": OP_EXECUTE_TOOL,
    }.get(node_type, OP_INVOKE_WORKFLOW)
    attrs = _clean(
        {
            OPERATION_NAME: operation,
            WORKFLOW_NAME: workflow_name,
            ORG_ID: org_id,
            WORKFLOW_RUN_ID: workflow_run_id,
            NODE_ID: node_id,
            NODE_TYPE: node_type,
            AGENT_RELEASE_ID: agent_release_id,
        }
    )
    with tracer.start_as_current_span(f"{operation} {node_id}", attributes=attrs) as span:
        yield span


def record_usage(
    span: Span,
    usage: dict[str, int],
    *,
    org_id: str,
    model_name: str,
    estimated: bool = False,
) -> None:
    """Set ``gen_ai.usage.*`` on the span and feed the token histogram."""
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    span.set_attribute(USAGE_INPUT_TOKENS, input_tokens)
    span.set_attribute(USAGE_OUTPUT_TOKENS, output_tokens)
    if estimated:
        # Provider did not return usage; downstream cost figures are a guess
        # and must not be presented as measured.
        span.set_attribute(USAGE_ESTIMATED, True)
    gen_ai_client_token_usage.labels(org_id, model_name, TOKEN_TYPE_INPUT).observe(input_tokens)
    gen_ai_client_token_usage.labels(org_id, model_name, TOKEN_TYPE_OUTPUT).observe(output_tokens)


def record_finish_reasons(span: Span, reasons: list[str]) -> None:
    if reasons:
        span.set_attribute(RESPONSE_FINISH_REASONS, reasons)


def capture_message_content() -> bool:
    """Whether prompt/completion bodies may be attached to spans.

    Off by default: message content routinely contains user PII and provider
    secrets, and the GenAI conventions treat content capture as opt-in.
    """
    return bool(getattr(settings, "otel_capture_message_content", False))