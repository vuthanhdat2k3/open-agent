"""M14 — deterministic replay.

The non-negotiable property: a replay must never execute a tool. If the
replayed run takes a different path than the recording, it stops and says
where, rather than quietly falling back to a live call that would cost
money and cause side effects.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import agent_loop as agent_loop_module
from app.core.agent_loop import _agent_stream
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.core.workflow.replay import (
    ReplayCursor,
    ReplayDiverged,
    arguments_hash,
    record_tool_call,
)
from app.db.base import Base
from app.models.agent import Agent
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.tool_call_record import ToolCallRecord

# Synthetic, non-functional — shaped like a key so the redactor fires.
SECRET_VALUE = "sk-replaytestsecret0123456789abcdefgh"

# Counts real executions so a test can prove replay never triggered one.
EXECUTIONS: dict[str, int] = {}


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed(db: AsyncSession, *, tools: list[str]) -> Agent:
    org = Organization(name="Replay Org", slug="replay-org")
    db.add(org)
    await db.commit()
    await db.refresh(org)

    provider = Provider(
        org_id=org.id, name="OpenAI", key="openai", base_url="http://x", api_key="k"
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    model = Model(
        org_id=org.id, provider_id=provider.id, name="gpt-4o-mini", display_name="GPT-4o mini"
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    agent = Agent(
        org_id=org.id,
        name="replayer",
        model_id=model.id,
        tools=tools,
        allowed_risk_tiers=["safe"],
        max_iterations=3,
        temperature=0.0,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


def _tool_call_delta(name: str, arguments: str) -> dict:
    return {"index": 0, "id": "call-1", "name": name, "arguments": arguments}


def _fake_stream(tool_name: str, arguments: str = "{}"):
    calls = {"n": 0}

    async def stream(self, messages, tools=None, temperature=0.7):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [_tool_call_delta(tool_name, arguments)]}
        else:
            yield {"type": "content", "text": "final"}
        yield {
            "type": "usage",
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "estimated": False,
            "finish_reasons": ["stop"],
        }

    return stream


def _counting_probe(name: str, output: str) -> None:
    EXECUTIONS[name] = 0

    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        EXECUTIONS[name] += 1
        return output

    register(
        ToolSpec(
            name=name,
            description="probe",
            input_schema={"type": "object", "properties": {}},
            run=_run,
            risk_tier=RiskTier.safe,
        )
    )


async def _drain(agent: Agent, db: AsyncSession, **kwargs) -> list[dict[str, Any]]:
    return [ev async for ev in _agent_stream(agent, "go", db, 0, "sess-replay", **kwargs)]


# --------------------------------------------------------------------------- #
# Argument hashing
# --------------------------------------------------------------------------- #
def test_arguments_hash_ignores_key_order() -> None:
    assert arguments_hash({"a": 1, "b": 2}) == arguments_hash({"b": 2, "a": 1})


def test_arguments_hash_detects_value_change() -> None:
    assert arguments_hash({"q": "x"}) != arguments_hash({"q": "y"})


# --------------------------------------------------------------------------- #
# Recording
# --------------------------------------------------------------------------- #
async def test_live_run_records_tool_calls(session_factory, monkeypatch) -> None:
    _counting_probe("replay_probe_record", "recorded output")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("replay_probe_record"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["replay_probe_record"])
        await _drain(agent, db)
        res = await db.execute(select(ToolCallRecord).where(ToolCallRecord.org_id == agent.org_id))
        records = list(res.scalars().all())

    assert len(records) == 1
    assert records[0].tool_name == "replay_probe_record"
    assert records[0].sequence == 1
    assert records[0].result == "recorded output"


async def test_recorded_result_is_redacted(session_factory, monkeypatch) -> None:
    """The recording must not become a credential store."""
    _counting_probe("replay_probe_secret", f"token {SECRET_VALUE} here")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("replay_probe_secret"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["replay_probe_secret"])
        await _drain(agent, db)
        res = await db.execute(select(ToolCallRecord).where(ToolCallRecord.org_id == agent.org_id))
        records = list(res.scalars().all())

    assert records
    assert SECRET_VALUE not in records[0].result


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #
async def test_replay_returns_recorded_output_without_executing(
    session_factory, monkeypatch
) -> None:
    _counting_probe("replay_probe_norun", "live output")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("replay_probe_norun"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["replay_probe_norun"])
        await _drain(agent, db)
        after_live = EXECUTIONS["replay_probe_norun"]

        cursor = await ReplayCursor.load(db, org_id=agent.org_id, session_id="sess-replay")
        # Fresh stream: the previous one already advanced past its tool-call
        # turn, so the replay run needs its own generator to request the tool.
        monkeypatch.setattr(
            agent_loop_module.LLMClient, "stream", _fake_stream("replay_probe_norun")
        )
        events = await _drain(agent, db, replay_cursor=cursor)

    assert after_live == 1, "the live run should have executed the tool once"
    assert EXECUTIONS["replay_probe_norun"] == 1, "replay must not execute the tool again"
    results = [e for e in events if e["event"] == "tool_result"]
    assert results and results[0]["data"]["result"] == "live output"


async def test_replay_diverges_instead_of_calling_a_missing_tool(
    session_factory, monkeypatch
) -> None:
    """An empty recording must halt the replay, not fall back to live calls."""
    _counting_probe("replay_probe_diverge", "never used")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("replay_probe_diverge"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["replay_probe_diverge"])
        events = await _drain(agent, db, replay_cursor=ReplayCursor([]))

    assert EXECUTIONS["replay_probe_diverge"] == 0, "replay must never execute a tool"
    diverged = [e for e in events if e["event"] == "replay_diverged"]
    assert diverged, "divergence must be reported explicitly"
    assert diverged[0]["data"]["requested"] == "replay_probe_diverge"


def test_cursor_reports_divergence_on_different_tool() -> None:
    record = ToolCallRecord(
        org_id="org-1",
        sequence=1,
        tool_name="expected_tool",
        arguments_hash=arguments_hash({}),
        arguments={},
        result="ok",
    )
    cursor = ReplayCursor([record])

    with pytest.raises(ReplayDiverged) as exc:
        cursor.next_result("other_tool", {})
    assert exc.value.expected == "expected_tool"
    assert exc.value.requested == "other_tool"


def test_cursor_reports_divergence_on_different_arguments() -> None:
    record = ToolCallRecord(
        org_id="org-1",
        sequence=1,
        tool_name="same_tool",
        arguments_hash=arguments_hash({"q": "original"}),
        arguments={"q": "original"},
        result="ok",
    )
    cursor = ReplayCursor([record])

    with pytest.raises(ReplayDiverged):
        cursor.next_result("same_tool", {"q": "changed"})


async def test_workflow_tool_node_records_then_replays_without_executing(
    session_factory,
) -> None:
    """End-to-end: a tool node runs once live, then never again on replay."""
    from app.core.workflow.engine import run_workflow
    from app.models.workflow import Workflow
    from app.models.workflow_run import WorkflowRun

    _counting_probe("replay_wf_probe", "workflow tool output")
    graph = {
        "nodes": [
            {"id": "in", "kind": "input"},
            {"id": "t", "kind": "tool", "config": {"tool": "replay_wf_probe"}},
            {"id": "out", "kind": "output"},
        ],
        "edges": [{"from_": "in", "to": "t"}, {"from_": "t", "to": "out"}],
    }

    async with session_factory() as db:
        org = Organization(name="WF Replay", slug="wf-replay")
        db.add(org)
        await db.commit()
        await db.refresh(org)

        wf = Workflow(org_id=org.id, name="ReplayWF", graph=graph)
        db.add(wf)
        await db.commit()
        await db.refresh(wf)

        _final, _log, source_run_id = await run_workflow(wf, "go", db)
        assert EXECUTIONS["replay_wf_probe"] == 1

        output, log, replay_run_id = await run_workflow(
            wf, "go", db, replay_of_run_id=source_run_id
        )

        res = await db.execute(select(WorkflowRun).where(WorkflowRun.id == replay_run_id))
        replay_run = res.scalar_one()

    assert EXECUTIONS["replay_wf_probe"] == 1, "replay must not execute the tool node again"
    assert "workflow tool output" in output
    assert replay_run.replay_of_run_id == source_run_id
    assert any(e["event"] == "replay_start" for e in log)


async def test_replay_is_tenant_scoped(session_factory) -> None:
    async with session_factory() as db:
        org = Organization(name="A", slug="org-a")
        other = Organization(name="B", slug="org-b")
        db.add_all([org, other])
        await db.commit()
        await db.refresh(org)
        await db.refresh(other)

        await record_tool_call(
            db,
            org_id=org.id,
            sequence=1,
            tool_name="t",
            arguments={},
            result="visible-only-to-org-a",
            session_id="s1",
            commit=True,
        )

        mine = await ReplayCursor.load(db, org_id=org.id, session_id="s1")
        theirs = await ReplayCursor.load(db, org_id=other.id, session_id="s1")

    assert len(mine) == 1
    assert len(theirs) == 0, "recordings must not leak across tenants"
