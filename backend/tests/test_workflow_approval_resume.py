"""C1 regression: a workflow approval node must resume after a decision.

Before the fix, deciding a workflow approval recorded the decision but never
re-drove the run, so any workflow with an approval node stayed stuck at
`waiting_approval` forever. These tests exercise the engine resume path that
the approvals endpoint triggers (via enqueue / detached run).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import run_workflow
from app.db.base import Base
from app.models.approval_request import ApprovalRequest
from app.models.organization import Organization
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun

_GRAPH = {
    "nodes": [
        {"id": "in", "kind": "input"},
        {"id": "gate", "kind": "approval"},
        {"id": "out", "kind": "output"},
    ],
    "edges": [{"from_": "in", "to": "gate"}, {"from_": "gate", "to": "out"}],
}


async def _seed(session: AsyncSession) -> Workflow:
    org = Organization(name="Approval Org", slug="approval-org")
    session.add(org)
    await session.commit()
    workflow = Workflow(org_id=org.id, name="Gated", graph=_GRAPH)
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)
    return workflow


async def _run_to_waiting(session: AsyncSession, workflow: Workflow) -> str:
    _final, events, run_id = await run_workflow(
        workflow, "payload", session, stream=False, force_inline=True, user_id="runner"
    )
    run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
    assert run is not None and run.status == "waiting_approval"
    assert any(ev["event"] == "approval_required" for ev in events)
    return run_id


async def _decide(session: AsyncSession, run_id: str, decision: str) -> None:
    approval = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.run_type == "workflow", ApprovalRequest.run_id == run_id
        )
    )
    assert approval is not None and approval.status == "pending"
    approval.status = decision
    await session.commit()


def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    return engine


async def test_approved_workflow_run_resumes_and_succeeds() -> None:
    engine = _factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        workflow = await _seed(session)
        run_id = await _run_to_waiting(session, workflow)

        await _decide(session, run_id, "approved")
        # The approvals endpoint flips the run back to a live status and
        # re-drives it; emulate that here.
        run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run.status = "running"
        await session.commit()

        final, _events, _ = await run_workflow(
            workflow, "payload", session, stream=False, force_inline=True, workflow_run_id=run_id
        )
        run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        assert run.status == "succeeded"
        assert final  # the run actually completed downstream of the gate
        # Exactly one approval request was ever created (no duplicate on resume).
        approvals = list(
            (
                await session.execute(
                    select(ApprovalRequest).where(ApprovalRequest.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(approvals) == 1
    await engine.dispose()


async def test_rejected_workflow_run_fails_at_gate() -> None:
    engine = _factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        workflow = await _seed(session)
        run_id = await _run_to_waiting(session, workflow)
        await _decide(session, run_id, "rejected")
        run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run.status = "running"
        await session.commit()

        await run_workflow(
            workflow, "payload", session, stream=False, force_inline=True, workflow_run_id=run_id
        )
        run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        assert run.status == "failed"
        assert "rejected" in (run.error or "")
    await engine.dispose()
