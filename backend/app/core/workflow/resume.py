"""Durable execution: resume a crashed workflow run exactly once.

No new checkpoint store is needed — ``workflow_node_runs.output`` already
records the result of every finished node. What was missing is the logic
that reads it back, plus a lease so two workers cannot pick up the same
orphaned run after a restart.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun

# A run that dies at the same node would otherwise be retried forever; after
# this many resumes it is failed with an explicit reason instead.
MAX_RESUME_ATTEMPTS = 3

# Long enough to survive a slow node, short enough that a killed worker's
# runs become claimable quickly. Workers extend it while they run.
DEFAULT_LEASE_SECONDS = 300

WORKER_ID = f"worker-{uuid.uuid4().hex[:12]}"


async def completed_node_outputs(db: AsyncSession, workflow_run_id: str) -> dict[str, Any]:
    """Return ``{node_id: output_dict}`` for nodes that already succeeded.

    Ordered by attempt so the latest successful attempt wins if a node was
    retried before eventually succeeding. The value carries the full
    ``{"text": ..., "data": ...}`` output so a resumed run rebuilds structured
    node outputs for downstream ``input_mapping`` and edge conditions.
    """
    res = await db.execute(
        select(WorkflowNodeRun)
        .where(
            WorkflowNodeRun.workflow_run_id == workflow_run_id,
            WorkflowNodeRun.status == "succeeded",
        )
        .order_by(WorkflowNodeRun.attempt)
    )
    out: dict[str, Any] = {}
    for row in res.scalars().all():
        out[row.node_id] = {
            "text": (row.output or {}).get("text", ""),
            "data": (row.output or {}).get("data", {}) or {},
        }
    return out


async def acquire_lease(
    db: AsyncSession,
    workflow_run_id: str,
    *,
    owner: str = WORKER_ID,
    ttl_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Try to claim a run. Returns ``True`` only for the winning worker.

    Conditional UPDATE rather than read-then-write: two workers racing on the
    same row cannot both observe a free lease, because the database
    serialises the update and only one matches the WHERE clause.
    """
    now = utc_now()
    expires = now + timedelta(seconds=ttl_seconds)
    result = await db.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == workflow_run_id,
            (WorkflowRun.lease_expires_at.is_(None)) | (WorkflowRun.lease_expires_at < now),
        )
        .values(lease_owner=owner, lease_expires_at=expires)
    )
    await db.commit()
    return bool(result.rowcount)


async def extend_lease(
    db: AsyncSession,
    workflow_run_id: str,
    *,
    owner: str = WORKER_ID,
    ttl_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Heartbeat: push the expiry out while this worker is still running."""
    result = await db.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == workflow_run_id, WorkflowRun.lease_owner == owner)
        .values(lease_expires_at=utc_now() + timedelta(seconds=ttl_seconds))
    )
    await db.commit()
    return bool(result.rowcount)


async def release_lease(db: AsyncSession, workflow_run_id: str, *, owner: str = WORKER_ID) -> None:
    """Drop the lease so a retry does not have to wait for expiry."""
    await db.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == workflow_run_id, WorkflowRun.lease_owner == owner)
        .values(lease_owner=None, lease_expires_at=None)
    )
    await db.commit()


async def find_orphaned_runs(db: AsyncSession) -> list[WorkflowRun]:
    """Runs still marked running whose lease lapsed — i.e. the worker died."""
    now = utc_now()
    res = await db.execute(
        select(WorkflowRun).where(
            WorkflowRun.status == "running",
            (WorkflowRun.lease_expires_at.is_(None)) | (WorkflowRun.lease_expires_at < now),
        )
    )
    return list(res.scalars().all())


async def mark_resumed(db: AsyncSession, workflow_run: WorkflowRun) -> bool:
    """Count one resume. Returns ``False`` when the run has exhausted them.

    Exhausting the budget fails the run with an explicit reason rather than
    leaving it running forever, so it surfaces in dashboards as a failure and
    not as a run that silently never finishes.
    """
    workflow_run.resume_count = (workflow_run.resume_count or 0) + 1
    if workflow_run.resume_count > MAX_RESUME_ATTEMPTS:
        workflow_run.status = "failed"
        workflow_run.error = (
            f"exceeded {MAX_RESUME_ATTEMPTS} resume attempts — "
            "the run keeps crashing at the same point"
        )
        workflow_run.finished_at = utc_now()
        await db.commit()
        return False
    await db.commit()
    return True


async def sweep_orphans(db: AsyncSession) -> list[str]:
    """Claim every orphaned run this worker can, returning their ids.

    Called on worker startup: a run whose worker was killed mid-flight is
    otherwise stuck in ``running`` with nothing driving it.
    """
    resumable: list[str] = []
    for run in await find_orphaned_runs(db):
        if not await acquire_lease(db, run.id):
            continue  # another worker claimed it first
        if await mark_resumed(db, run):
            resumable.append(run.id)
        else:
            await release_lease(db, run.id)
    return resumable
