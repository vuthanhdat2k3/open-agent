"""Approval requests raised by a delegated sub-agent must pause the root run.

Root cause this guards against: `call_agent` / `delegate_to_*` execute a
sub-agent loop that can itself hit an approval gate. Before this fix, the
sub-agent's approval only paused the *sub*-task; the delegate tool call
returned a plain string like "approval required for X (approval_id: ...)"
to the parent model, which read it as an ordinary tool result, wrote a
text reply asking the user to approve, and let the root run finish as
"succeeded" - with the approval permanently pending and no
`approval_required` event ever emitted for the root run, so the chat UI
never rendered an approve/reject action.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import agent_loop as agent_loop_module
from app.core.agent_loop import _agent_stream
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.db.base import Base
from app.models.agent import Agent
from app.models.approval_request import ApprovalRequest
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed_org(db: AsyncSession) -> tuple[Organization, Model]:
    org = Organization(name="Delegation Org", slug="delegation-org")
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
    return org, model


async def _seed_agents(db: AsyncSession) -> tuple[Agent, Agent]:
    """An orchestrator that can `call_agent`, and a worker with a
    requires_approval tool."""
    org, model = await _seed_org(db)

    worker = Agent(
        org_id=org.id,
        name="email-worker",
        model_id=model.id,
        tools=["send_gated_email"],
        allowed_risk_tiers=["safe", "execute"],
        max_iterations=3,
        temperature=0.0,
    )
    db.add(worker)
    await db.commit()
    await db.refresh(worker)

    orchestrator = Agent(
        org_id=org.id,
        name="orchestrator",
        kind="orchestrator",
        model_id=model.id,
        tools=["call_agent"],
        allowed_risk_tiers=["safe", "execute"],
        max_iterations=3,
        temperature=0.0,
    )
    db.add(orchestrator)
    await db.commit()
    await db.refresh(orchestrator)
    return orchestrator, worker


def _tool_call_delta(name: str, arguments: str) -> dict:
    return {"index": 0, "id": "call-1", "name": name, "arguments": arguments}


def _fake_stream_sequence(turns: list[dict]):
    """Yields one scripted turn per call, repeating the last turn forever
    (the worker's post-approval-block turn and the orchestrator's next turn
    each consume one call)."""
    calls = {"n": 0}

    async def stream(self, messages, tools=None, temperature=0.7, tool_choice=None, thinking=None):  # noqa: ANN001
        idx = min(calls["n"], len(turns) - 1)
        calls["n"] += 1
        turn = turns[idx]
        if turn["type"] == "tool_calls":
            yield {
                "type": "tool_calls",
                "tool_calls": [_tool_call_delta(turn["name"], turn.get("arguments", "{}"))],
            }
        else:
            yield {"type": "content", "text": turn.get("text", "")}
        yield {
            "type": "usage",
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "estimated": False,
            "finish_reasons": ["stop"],
        }

    return stream


def _register_gated_tool() -> None:
    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        return "should never execute without approval"

    register(
        ToolSpec(
            name="send_gated_email",
            description="Send an email (requires human approval).",
            input_schema={"type": "object", "properties": {}},
            run=_run,
            risk_tier=RiskTier.execute,
            requires_approval=True,
        )
    )


async def _drain(agent: Agent, db: AsyncSession, **kwargs) -> list[dict[str, Any]]:
    return [ev async for ev in _agent_stream(agent, "go", db, 0, "sess-delegate", **kwargs)]


async def test_subagent_approval_pauses_the_root_run(session_factory, monkeypatch) -> None:
    _register_gated_tool()
    async with session_factory() as db:
        orchestrator, worker = await _seed_agents(db)

        # Turn 1 (orchestrator): delegate to the worker via call_agent.
        # Turn 2 (worker, nested loop): call the gated tool -> approval gate.
        monkeypatch.setattr(
            agent_loop_module.LLMClient,
            "stream",
            _fake_stream_sequence(
                [
                    {
                        "type": "tool_calls",
                        "name": "call_agent",
                        "arguments": (
                            f'{{"target_agent_id": "{worker.id}", '
                            '"instruction": "send the email"}'
                        ),
                    },
                    {
                        "type": "tool_calls",
                        "name": "send_gated_email",
                        "arguments": "{}",
                    },
                ]
            ),
        )

        events = await _drain(orchestrator, db)

        approvals = (
            await db.execute(
                agent_loop_module.select(ApprovalRequest).where(
                    ApprovalRequest.org_id == orchestrator.org_id
                )
            )
        ).scalars().all()

    assert len(approvals) == 1, "the sub-agent's tool call must create exactly one approval"
    approval = approvals[0]
    assert approval.status == "pending"
    assert approval.tool_name == "send_gated_email"

    # The root run must have paused for approval, not answered as if the
    # sub-agent's text summary were a final answer.
    approval_events = [e for e in events if e["event"] == "approval_required"]
    assert approval_events, "root run must emit approval_required, not silently finish"
    assert approval_events[0]["data"]["approval_id"] == approval.id
    assert approval_events[0]["data"]["tool_name"] == "send_gated_email"

    done_events = [e for e in events if e["event"] == "message_done"]
    assert not done_events, "root run must not finish as succeeded while approval is pending"


async def test_subagent_approval_records_owning_task_id(session_factory, monkeypatch) -> None:
    """The approval must remember which task actually owns the gated call,
    not just the shared root_run_id - that ownership is what lets a resume
    execute in the right agent's context instead of the root's."""
    _register_gated_tool()
    async with session_factory() as db:
        orchestrator, worker = await _seed_agents(db)
        monkeypatch.setattr(
            agent_loop_module.LLMClient,
            "stream",
            _fake_stream_sequence(
                [
                    {
                        "type": "tool_calls",
                        "name": "call_agent",
                        "arguments": (
                            f'{{"target_agent_id": "{worker.id}", '
                            '"instruction": "send the email"}'
                        ),
                    },
                    {"type": "tool_calls", "name": "send_gated_email", "arguments": "{}"},
                ]
            ),
        )
        await _drain(orchestrator, db)

        approval = (
            (
                await db.execute(
                    agent_loop_module.select(ApprovalRequest).where(
                        ApprovalRequest.org_id == orchestrator.org_id
                    )
                )
            )
            .scalars()
            .first()
        )
        sub_task = (
            (
                await db.execute(
                    agent_loop_module.select(agent_loop_module.Task).where(
                        agent_loop_module.Task.agent_id == worker.id
                    )
                )
            )
            .scalars()
            .first()
        )

    assert approval.owning_task_id == sub_task.id
    assert approval.owning_task_id != sub_task.parent_task_id


async def test_approve_resumes_the_owning_subagent_and_root_continues(
    session_factory, monkeypatch
) -> None:
    """Approving must execute the tool in the worker's context (it has the
    tool; the orchestrator does not), then let the orchestrator's own loop
    continue and produce a final answer - not 'tool not available'."""
    _register_gated_tool()
    async with session_factory() as db:
        orchestrator, worker = await _seed_agents(db)
        monkeypatch.setattr(
            agent_loop_module.LLMClient,
            "stream",
            _fake_stream_sequence(
                [
                    {
                        "type": "tool_calls",
                        "name": "call_agent",
                        "arguments": (
                            f'{{"target_agent_id": "{worker.id}", '
                            '"instruction": "send the email"}'
                        ),
                    },
                    {"type": "tool_calls", "name": "send_gated_email", "arguments": "{}"},
                ]
            ),
        )
        events = await _drain(orchestrator, db)
        approval_id = next(e["data"]["approval_id"] for e in events if e["event"] == "approval_required")

        root_task = (
            (
                await db.execute(
                    agent_loop_module.select(agent_loop_module.Task).where(
                        agent_loop_module.Task.agent_id == orchestrator.id
                    )
                )
            )
            .scalars()
            .first()
        )

        approval = (
            await db.execute(
                agent_loop_module.select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
            )
        ).scalar_one()
        approval.status = "approved"
        await db.commit()

        # Resuming re-runs the orchestrator's turn. The next model call (the
        # worker's post-tool-result turn) must produce a final answer for
        # the resume to reach message_done rather than looping forever.
        monkeypatch.setattr(
            agent_loop_module.LLMClient,
            "stream",
            _fake_stream_sequence([{"type": "content", "text": "email sent, all done"}]),
        )

        resume_events = await _drain(
            orchestrator,
            db,
            current_task_id=root_task.id,
            approval_resume_id=approval_id,
        )

    errors = [e for e in resume_events if e["event"] == "error"]
    assert not errors, f"resume must not error, got: {errors}"

    done_events = [e for e in resume_events if e["event"] == "message_done"]
    assert done_events, "the orchestrator's run must reach a final answer after resuming"

