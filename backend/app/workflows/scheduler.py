from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import gen_id, utc_now
from app.models.outbox import OutboxEvent
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_occurrence import WorkflowOccurrence
from app.models.workflow_run import WorkflowRun


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


async def run_due_workflows(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    current = now or utc_now()
    result = await db.execute(
        select(WorkflowInstallation)
        .where(WorkflowInstallation.status == "enabled", WorkflowInstallation.next_run_at.is_not(None), WorkflowInstallation.next_run_at <= current)
        .order_by(WorkflowInstallation.next_run_at)
        .limit(100)
    )
    installations = list(result.scalars().all())
    queued = 0
    for installation in installations:
        scheduled_for = installation.next_run_at
        if scheduled_for is None:
            continue
        occurrence_key = scheduled_for.isoformat(timespec="minutes")
        existing = await db.scalar(
            select(WorkflowOccurrence).where(
                WorkflowOccurrence.installation_id == installation.id,
                WorkflowOccurrence.occurrence_key == occurrence_key,
            )
        )
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
            queued += 1
        installation.next_run_at = next_run_at(installation.schedule, installation.timezone, now=current)
    await db.commit()
    return {"due": len(installations), "queued": queued}
