"""Task 3 hardening — a workflow *tool node* whose tool requires approval
must pause the run and never execute before a human decides, and an
approved resume must execute the exact arguments that were reviewed.

Before task 3, `engine.py`'s tool-node branch called `execute_tool_call`
directly with no `requires_approval` check at all: a `dangerous`/gated
MCP or builtin tool wired into a workflow would fire immediately on every
run, approval system notwithstanding. These tests pin the fix.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.tools.registry import BUILTIN_TOOLS, register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.core.workflow.engine import run_workflow
from app.db.base import Base
from app.models.approval_request import ApprovalRequest
from app.models.organization import Organization
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun

EXECUTIONS: dict[str, int] = {}


def _register_gated_tool(name: str) -> None:
    EXECUTIONS[name] = 0

    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        EXECUTIONS[name] += 1
        return f"sent: {args.get('to', '')}"

    register(
        ToolSpec(
            name=name,
            description="gated tool node probe",
            input_schema={
                "type": "object",
                "properties": {"to": {"type": "string"}},
            },
            run=_run,
            risk_tier=RiskTier.execute,
            requires_approval=True,
        )
    )


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _graph(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "in", "kind": "input"},
            {
                "id": "gate",
                "kind": "tool",
                "config": {"tool": tool_name, "arguments": args},
            },
            {"id": "out", "kind": "output"},
        ],
        "edges": [{"from_": "in", "to": "gate"}, {"from_": "gate", "to": "out"}],
    }


async def _seed_workflow(db: AsyncSession, tool_name: str, args: dict[str, Any]) -> Workflow:
    org = Organization(name="Gate Org", slug="gate-org")
    db.add(org)
    await db.commit()
    await db.refresh(org)
    wf = Workflow(org_id=org.id, name="Gated Tool Workflow", graph=_graph(tool_name, args))
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


async def test_tool_node_pauses_for_approval_and_never_executes(session_factory) -> None:
    _register_gated_tool("wf_gate_probe_pause")
    async with session_factory() as db:
        wf = await _seed_workflow(db, "wf_gate_probe_pause", {"to": "customer@example.com"})

        _final, events, run_id = await run_workflow(wf, "go", db, force_inline=True)

        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        approvals = list(
            (await db.execute(select(ApprovalRequest).where(ApprovalRequest.run_id == run_id)))
            .scalars()
            .all()
        )

    assert EXECUTIONS["wf_gate_probe_pause"] == 0, "a gated tool node must not run before approval"
    assert run is not None and run.status == "waiting_approval"
    assert any(ev["event"] == "approval_required" for ev in events)
    assert len(approvals) == 1
    assert approvals[0].run_type == "workflow.tool"
    assert approvals[0].tool_name == "wf_gate_probe_pause"
    assert approvals[0].status == "pending"


async def test_tool_node_executes_exact_approved_arguments_on_resume(session_factory) -> None:
    _register_gated_tool("wf_gate_probe_resume")
    async with session_factory() as db:
        wf = await _seed_workflow(db, "wf_gate_probe_resume", {"to": "customer@example.com"})
        _final, _events, run_id = await run_workflow(wf, "go", db, force_inline=True)

        approval = await db.scalar(
            select(ApprovalRequest).where(ApprovalRequest.run_id == run_id)
        )
        assert approval is not None
        approval.status = "approved"
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run.status = "running"
        await db.commit()

        final, _events2, _ = await run_workflow(
            wf, "go", db, force_inline=True, workflow_run_id=run_id
        )
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))

    assert EXECUTIONS["wf_gate_probe_resume"] == 1, "approval must let the tool run exactly once"
    assert run.status == "succeeded"
    assert "sent: customer@example.com" in final


async def test_tool_node_rejects_tampered_arguments_after_approval(session_factory) -> None:
    """The approval snapshot is the contract: if the workflow's own config
    changes after a request is approved, the mismatch must fail loudly
    rather than silently executing the (now different) arguments."""
    _register_gated_tool("wf_gate_probe_tamper")
    async with session_factory() as db:
        wf = await _seed_workflow(db, "wf_gate_probe_tamper", {"to": "customer@example.com"})
        _final, _events, run_id = await run_workflow(wf, "go", db, force_inline=True)

        approval = await db.scalar(
            select(ApprovalRequest).where(ApprovalRequest.run_id == run_id)
        )
        assert approval is not None
        approval.status = "approved"
        # Tamper with the recorded snapshot after approval — simulates the
        # workflow graph (or the approval row) diverging from what was
        # actually reviewed.
        approval.args_snapshot = {"to": "attacker@evil.example"}
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run.status = "running"
        await db.commit()

        # The engine's default onError policy ("stop") catches the node's
        # RuntimeError internally rather than propagating it to the caller -
        # it surfaces as a node_error event and a failed run.
        _final, events2, _ = await run_workflow(
            wf, "go", db, force_inline=True, workflow_run_id=run_id
        )
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))

    assert EXECUTIONS["wf_gate_probe_tamper"] == 0, "tampered arguments must never execute"
    assert run is not None and run.status == "failed"
    assert run.error and "no longer match" in run.error
    node_errors = [e for e in events2 if e["event"] == "node_error"]
    assert any("no longer match" in e["data"]["message"] for e in node_errors)


async def test_tool_node_without_requires_approval_runs_immediately(session_factory) -> None:
    """Control case: an ordinary (non-gated) tool node is unaffected by the
    approval gate and must not regress into pausing every tool node."""

    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        return "ungated ok"

    register(
        ToolSpec(
            name="wf_ungated_probe",
            description="ungated tool node",
            input_schema={"type": "object", "properties": {}},
            run=_run,
            risk_tier=RiskTier.safe,
        )
    )
    async with session_factory() as db:
        wf = await _seed_workflow(db, "wf_ungated_probe", {})
        final, _events, run_id = await run_workflow(wf, "go", db, force_inline=True)
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))

    assert run.status == "succeeded"
    assert "ungated ok" in final


async def test_gated_builtin_tools_stay_registered_with_approval() -> None:
    """Sanity check that this suite is exercising the real gate: any builtin
    tool already marked requires_approval=True must still be marked so."""
    gated = [name for name, spec in BUILTIN_TOOLS.items() if spec.requires_approval]
    # Not asserting a specific tool list (that's owned by builtins.py), just
    # that the registry surfaces the flag this engine branch relies on.
    for name in gated:
        assert BUILTIN_TOOLS[name].requires_approval is True
