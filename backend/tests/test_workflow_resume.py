"""M14 — resume a crashed workflow run exactly once.

The properties that matter operationally:

* a node that already succeeded is never executed twice (side effects!),
* two workers cannot both drive the same orphaned run,
* a run that keeps dying at the same node fails instead of looping forever.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow import resume
from app.core.workflow.engine import run_workflow
from app.db.base import Base, utc_now
from app.models.organization import Organization
from app.models.workflow import Workflow
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun

GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "kind": "input"},
        {"id": "mid", "kind": "merge"},
        {"id": "out", "kind": "output"},
    ],
    "edges": [
        {"from_": "in", "to": "mid"},
        {"from_": "mid", "to": "out"},
    ],
}


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed(db: AsyncSession) -> Workflow:
    org = Organization(name="Resume Org", slug="resume-org")
    db.add(org)
    await db.commit()
    await db.refresh(org)

    wf = Workflow(org_id=org.id, name="Resumable", graph=GRAPH)
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


async def _node_runs(db: AsyncSession, run_id: str, node_id: str) -> list[WorkflowNodeRun]:
    res = await db.execute(
        select(WorkflowNodeRun).where(
            WorkflowNodeRun.workflow_run_id == run_id,
            WorkflowNodeRun.node_id == node_id,
        )
    )
    return list(res.scalars().all())


# --------------------------------------------------------------------------- #
# Checkpoint reuse
# --------------------------------------------------------------------------- #
async def test_completed_nodes_are_not_executed_again(session_factory) -> None:
    """The core resume guarantee: no duplicate execution of finished nodes."""
    async with session_factory() as db:
        wf = await _seed(db)

        await run_workflow(wf, "hello", db)
        res = await db.execute(select(WorkflowRun).where(WorkflowRun.workflow_id == wf.id))
        run = res.scalars().first()
        assert run is not None
        before = {n: len(await _node_runs(db, run.id, n)) for n in ("in", "mid", "out")}

        # Re-entering the same run must reuse recorded outputs rather than
        # creating a second node_run for anything already succeeded.
        await run_workflow(wf, "hello", db, workflow_run_id=run.id)
        after = {n: len(await _node_runs(db, run.id, n)) for n in ("in", "mid", "out")}

    assert after == before, "resume must not re-execute already-succeeded nodes"


async def test_completed_node_outputs_reads_back_recorded_text(session_factory) -> None:
    async with session_factory() as db:
        wf = await _seed(db)
        await run_workflow(wf, "payload-xyz", db)
        res = await db.execute(select(WorkflowRun).where(WorkflowRun.workflow_id == wf.id))
        run = res.scalars().first()

        outputs = await resume.completed_node_outputs(db, run.id)

    assert outputs["in"] == {"text": "payload-xyz", "data": {"input": "payload-xyz"}}
    assert set(outputs) == {"in", "mid", "out"}


# --------------------------------------------------------------------------- #
# Lease
# --------------------------------------------------------------------------- #
async def test_only_one_worker_can_claim_a_run(session_factory) -> None:
    async with session_factory() as db:
        wf = await _seed(db)
        run = WorkflowRun(org_id=wf.org_id, workflow_id=wf.id, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)

        first = await resume.acquire_lease(db, run.id, owner="worker-a")
        second = await resume.acquire_lease(db, run.id, owner="worker-b")

    assert first is True
    assert second is False, "a leased run must not be claimable by a second worker"


async def test_expired_lease_becomes_claimable(session_factory) -> None:
    async with session_factory() as db:
        wf = await _seed(db)
        run = WorkflowRun(
            org_id=wf.org_id,
            workflow_id=wf.id,
            status="running",
            lease_owner="dead-worker",
            lease_expires_at=utc_now() - timedelta(seconds=1),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        claimed = await resume.acquire_lease(db, run.id, owner="fresh-worker")
        await db.refresh(run)

    assert claimed is True
    assert run.lease_owner == "fresh-worker"


async def test_release_lets_another_worker_take_over(session_factory) -> None:
    async with session_factory() as db:
        wf = await _seed(db)
        run = WorkflowRun(org_id=wf.org_id, workflow_id=wf.id, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)

        await resume.acquire_lease(db, run.id, owner="worker-a")
        await resume.release_lease(db, run.id, owner="worker-a")
        taken = await resume.acquire_lease(db, run.id, owner="worker-b")

    assert taken is True


# --------------------------------------------------------------------------- #
# Crash-loop protection
# --------------------------------------------------------------------------- #
async def test_resume_budget_fails_the_run_instead_of_looping(session_factory) -> None:
    async with session_factory() as db:
        wf = await _seed(db)
        run = WorkflowRun(org_id=wf.org_id, workflow_id=wf.id, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)

        allowed = [await resume.mark_resumed(db, run) for _ in range(resume.MAX_RESUME_ATTEMPTS)]
        exhausted = await resume.mark_resumed(db, run)
        await db.refresh(run)

    assert all(allowed), "resumes within budget must be permitted"
    assert exhausted is False
    assert run.status == "failed"
    assert "resume attempts" in (run.error or ""), "the failure reason must be explicit"


async def test_sweep_claims_orphans_and_skips_healthy_runs(session_factory) -> None:
    async with session_factory() as db:
        wf = await _seed(db)
        orphan = WorkflowRun(
            org_id=wf.org_id,
            workflow_id=wf.id,
            status="running",
            lease_expires_at=utc_now() - timedelta(seconds=5),
        )
        healthy = WorkflowRun(
            org_id=wf.org_id,
            workflow_id=wf.id,
            status="running",
            lease_owner="live-worker",
            lease_expires_at=utc_now() + timedelta(seconds=120),
        )
        finished = WorkflowRun(org_id=wf.org_id, workflow_id=wf.id, status="succeeded")
        db.add_all([orphan, healthy, finished])
        await db.commit()
        for r in (orphan, healthy, finished):
            await db.refresh(r)

        claimed = await resume.sweep_orphans(db)

    assert orphan.id in claimed
    assert healthy.id not in claimed, "a live worker's run must not be stolen"
    assert finished.id not in claimed, "only running runs are resumable"
