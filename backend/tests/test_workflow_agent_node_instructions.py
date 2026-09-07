"""Agent-kind workflow nodes must actually use their `instructions` config.

Regression for a bug found via live testing: `_run_agent_node` built the
agent's message from upstream node output alone and silently dropped
`cfg["instructions"]` — a per-step task ask that workflow_generate (and hand
-authored workflows) commonly set on agent nodes. Every agent node in every
workflow was affected.
"""

from __future__ import annotations

import pytest

from app.core.workflow.engine import _run_agent_node


class _FakeLoopResult:
    content = "ok"
    usage = None
    cost_usd = None
    latency_ms = None
    tool_calls = None
    error = None


@pytest.mark.parametrize(
    "instructions,upstream_text,expect_in_text",
    [
        ("Search for tech news from the last 24 hours.", "trigger fired", [
            "Search for tech news from the last 24 hours.",
            "trigger fired",
        ]),
        ("", "trigger fired", ["trigger fired"]),
    ],
)
async def test_agent_node_layers_instructions_onto_upstream_text(
    monkeypatch, instructions, upstream_text, expect_in_text
):
    captured: dict[str, str] = {}

    async def fake_run_agent_loop(agent, text, db, **kwargs):
        captured["text"] = text
        return _FakeLoopResult()

    monkeypatch.setattr("app.core.agent_loop.run_agent_loop", fake_run_agent_loop)

    node = {"id": "research", "_org_id": "org1"}
    cfg = {
        "mode": "custom",
        "model_id": "model-1",
        "instructions": instructions,
    }
    await _run_agent_node(
        node, cfg, node_run=None, upstream_text=upstream_text,
        db=None, actor_user_id=None, actor_user_role=None,
    )

    for fragment in expect_in_text:
        assert fragment in captured["text"]


async def test_agent_node_fails_when_loop_reports_an_error(monkeypatch):
    """A terminal agent-loop failure (budget exceeded, provider error, ...)
    surfaces as an empty `content` with `error` set, never as a raised
    exception from run_agent_loop itself. Regression for a bug found live:
    the node reported "succeeded" with blank output and fed that emptiness
    to every downstream node instead of stopping the run.
    """

    class _FailedLoopResult:
        content = ""
        usage = None
        cost_usd = None
        latency_ms = None
        tool_calls = None
        error = "run budget exceeded: max_tool_calls exceeded (41>40)"

    async def fake_run_agent_loop(agent, text, db, **kwargs):
        return _FailedLoopResult()

    monkeypatch.setattr("app.core.agent_loop.run_agent_loop", fake_run_agent_loop)

    node = {"id": "research", "_org_id": "org1"}
    cfg = {"mode": "custom", "model_id": "model-1"}
    with pytest.raises(RuntimeError, match="run budget exceeded"):
        await _run_agent_node(
            node, cfg, node_run=None, upstream_text="trigger fired",
            db=None, actor_user_id=None, actor_user_role=None,
        )
