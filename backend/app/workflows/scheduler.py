from __future__ import annotations

import structlog
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import gen_id, utc_now
from app.models.outbox import OutboxEvent
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_occurrence import WorkflowOccurrence
from app.models.workflow_run import WorkflowRun

logger = structlog.get_logger(__name__)

# Batches keep the per-tick transaction small so a single bad row does not
# blow up a 100-installation sweep. 10 is a conservative default; tune via
# observation in production.
_SCHEDULER_BATCH_SIZE = 10


def _local_now(now: datetime, timezone_name: str) -> datetime:
    aware = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    return aware.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)


def next_run_at(schedule: dict, timezone_name: str, *, now: datetime | None = None) -> datetime | None:
    """Return the next wall-clock occurrence as naive UTC for persistence."""
    current_utc = now or utc_now()
    local = _local_now(current_utc, timezone_name)
    kind = schedule.get("kind", "daily")
    if kind == "event":
        return None
    if kind == "hourly":
        interval = max(1, min(int(schedule.get("interval_hours") or 1), 12))
        candidate = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=interval)
    else:
        hour, minute = (int(part) for part in str(schedule.get("time") or "07:30").split(":"))
        candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local:
            candidate += timedelta(days=1)
        if kind == "weekdays":
            while candidate.weekday() >= 5:
                candidate += timedelta(days=1)
        elif kind == "weekly":
            wanted = int(schedule.get("weekday") or 0)
            while candidate.weekday() != wanted:
                candidate += timedelta(days=1)
    return candidate.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc).replace(tzinfo=None)


async def _process_installation(
    db: AsyncSession, installation: WorkflowInstallation, current: datetime
) -> bool:
    """Queue one due installation. Returns True on success, False on no-op.

    A failure here (bad timezone, DB constraint, etc.) propagates as an
    exception so the caller can roll back just this row and advance its
    ``next_run_at`` in a fresh transaction.
    """
    scheduled_for = installation.next_run_at
    if scheduled_for is None:
        return False
    occurrence_key = scheduled_for.isoformat(timespec="minutes")
    existing = await db.scalar(
        select(WorkflowOccurrence).where(
            WorkflowOccurrence.installation_id == installation.id,
            WorkflowOccurrence.occurrence_key == occurrence_key,
        )
    )
    active_occurrence = await db.scalar(
        select(WorkflowOccurrence.id).where(
            WorkflowOccurrence.installation_id == installation.id,
            WorkflowOccurrence.status.in_({"queued", "dispatched", "running"}),
        )
    )
    if active_occurrence is not None:
        installation.next_run_at = next_run_at(
            installation.schedule, installation.timezone, now=current
        )
        return True
    if existing is None:
        occurrence_id = gen_id()
        run = WorkflowRun(
            org_id=installation.org_id,
            workflow_id=installation.workflow_id,
            status="queued",
            input={
                "text": "",
                "timezone": installation.timezone,
                "trigger": "scheduled",
                "installation_id": installation.id,
                "template_key": installation.template_key,
                "template_version": installation.template_version,
                "occurrence_id": occurrence_id,
            },
            triggered_by_user_id=installation.owner_user_id,
        )
        db.add(run)
        await db.flush()
        occurrence = WorkflowOccurrence(
            id=occurrence_id,
            installation_id=installation.id,
            workflow_run_id=run.id,
            occurrence_key=occurrence_key,
            scheduled_for=scheduled_for,
            status="queued",
            payload={"template_key": installation.template_key},
        )
        db.add(occurrence)
        db.add(OutboxEvent(
            event_type="workflow.run.requested",
            aggregate_type="workflow_occurrence",
            aggregate_id=occurrence.id,
            org_id=installation.org_id,
            user_id=installation.owner_user_id,
            correlation_id=occurrence.id,
            payload={"run_id": run.id, "installation_id": installation.id},
            dedupe_key=f"{installation.id}:{occurrence_key}",
        ))
    installation.next_run_at = next_run_at(installation.schedule, installation.timezone, now=current)
    return True


async def _advance_next_run_at(db: AsyncSession, installation_id: str) -> None:
    """Best-effort: reload the installation and advance its ``next_run_at``.

    Used after a per-installation rollback so a poison row does not get
    re-picked by the very next tick. Swallows further errors so the
    scheduler does not crash on persistent poison rows.
    """
    try:
        fresh = await db.get(WorkflowInstallation, installation_id)
        if fresh is None:
            return
        fresh.next_run_at = next_run_at(fresh.schedule, fresh.timezone, now=utc_now())
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        await logger.aerror(
            "workflow_scheduler_advance_next_run_failed",
            installation_id=installation_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def run_due_workflows(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Materialize due personal workflow occurrences through the durable outbox.

    Each installation is processed in its own try/except so a single bad row
    (bad timezone, DB constraint, etc.) does not roll back the work for the
    rest of the batch. Commits happen per-batch so the transaction size
    stays bounded and the failure radius is small.
    """
    current = now or utc_now()
    result = await db.execute(
        select(WorkflowInstallation)
        .where(WorkflowInstallation.status == "enabled", WorkflowInstallation.next_run_at.is_not(None), WorkflowInstallation.next_run_at <= current)
        .order_by(WorkflowInstallation.next_run_at)
        .limit(100)
    )
    installations = list(result.scalars().all())
    queued = 0
    failed = 0

    for batch_start in range(0, len(installations), _SCHEDULER_BATCH_SIZE):
        batch = installations[batch_start:batch_start + _SCHEDULER_BATCH_SIZE]
        for installation in batch:
            try:
                if await _process_installation(db, installation, current):
                    await db.flush()
                    # Count only the runs we just added (not the no-op early
                    # returns that only bump ``next_run_at``). Iterate the
                    # session's pending objects once per row.
                    for obj in db.new:
                        if (
                            isinstance(obj, WorkflowRun)
                            and obj.input
                            and obj.input.get("installation_id") == installation.id
                            and obj.input.get("trigger") == "scheduled"
                        ):
                            queued += 1
                            break
            except Exception as exc:  # noqa: BLE001
                failed += 1
                await db.rollback()
                await logger.aerror(
                    "workflow_scheduler_installation_failed",
                    installation_id=installation.id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                # Best-effort: advance the row in a fresh tx so the next tick
                # does not re-pick the same poison row.
                await _advance_next_run_at(db, installation.id)
        # Commit the whole batch's writes at the end. A failure here rolls
        # back the whole batch (and is reported as a single failure for
        # every row in it) — but with per-installation ``try`` above, an
        # exception is only thrown by infrastructure-level problems
        # (connection drop, etc.) where rolling back the batch is the
        # right call anyway.
        try:
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            failed += len(batch)
            await logger.aerror(
                "workflow_scheduler_batch_commit_failed",
                batch_start=batch_start,
                batch_size=len(batch),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            for installation in batch:
                await _advance_next_run_at(db, installation.id)

    return {"due": len(installations), "queued": queued, "failed": failed}
