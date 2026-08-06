"""M6 - Customer Intelligence scheduler.

Drives periodic per-timezone daily syncs for ``CiSchedule`` rows. The worker
calls :func:`run_due_schedules` on a short cron cadence; only schedules whose
``next_run_at`` has passed are synced, and each run advances ``last_run_at`` /
``next_run_at`` to the next wall-clock occurrence.

Timezone handling is the subtle part: models persist naive UTC (see
``app.db.base.utc_now``), so :func:`compute_next_run_at` computes the next
wall-clock occurrence in the schedule's zone and converts back to naive UTC.
DST transitions are handled naturally by ``zoneinfo``.

Metrics are emitted by :func:`app.customer_intelligence.ingest.sync_connection`
(single writer for both manual and scheduled syncs); this module only isolates
failures so one bad schedule never kills the tick.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.customer_intelligence.ingest import IngestionError, sync_connection
from app.db.base import gen_id, utc_now
from app.models.customer_intelligence import CiSchedule
from app.repositories.customer_intelligence import CiScheduleRepository

logger = structlog.get_logger(__name__)

# Bound the payload size per scheduled sync (mirrors the manual default).
SCHEDULED_MAX_MESSAGES = 20

# ponytail: process-local lock prevents overlapping ticks in one worker;
# use a Redis/DB lease if multiple worker processes share schedules.
_scheduler_tick_lock = asyncio.Lock()


def _coerce_zone(tz_name: str) -> ZoneInfo:
    """Resolve an IANA zone name; fall back to UTC for unknown/bad names.

    A bad ``timezone`` value must never take the whole scheduler down - the rest
    of an org's schedules should keep firing.
    """
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("UTC")


def compute_next_run_at(run_time: str, timezone_: str, now: datetime | None = None) -> datetime:
    """Next wall-clock ``run_time`` (``HH:MM``) in ``timezone_`` strictly after ``now``.

    ``now`` is naive UTC (matching the model layer) and the result is also naive
    UTC. If the run time on ``now``'s local calendar day has already passed, the
    next day's occurrence is returned (DST-aware via zoneinfo).
    """
    now = now or utc_now()
    parts = run_time.split(":")
    if len(parts) != 2:
        raise ValueError("run_time must be HH:MM")
    hour, minute = (int(part) for part in parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("run_time must be HH:MM")
    zone = _coerce_zone(timezone_)

    # Interpret naive ``now`` as UTC, then project into the target zone.
    aware_now = now.replace(tzinfo=timezone.utc).astimezone(zone)
    candidate = aware_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= aware_now:
        candidate += timedelta(days=1)
    # Back to naive UTC for persistence.
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


async def _run_due_schedules_unlocked(
    db: AsyncSession, *, now: datetime | None = None, actor_user_id: str | None = None
) -> dict[str, Any]:
    """Sync every due schedule once and advance its next run.

    Returns a summary dict for logging/testing. A failure on one schedule is
    isolated so the rest still run.
    """
    now = now or utc_now()
    repo = CiScheduleRepository(db)
    due = await repo.list_due(now)

    processed: list[str] = []
    failed: list[tuple[str, str]] = []

    for schedule in due:
        try:
            await _run_one(db, schedule, now=now, actor_user_id=actor_user_id)
        except Exception as exc:  # noqa: BLE001 - never let one schedule kill the tick.
            failed.append((schedule.id, str(exc)))
            await logger.aerror(
                "ci_scheduled_sync_failed",
                schedule_id=schedule.id,
                error=str(exc),
            )
            continue

        processed.append(schedule.id)

    return {"due": len(due), "processed": processed, "failed": failed}


async def run_due_schedules(
    db: AsyncSession, *, now: datetime | None = None, actor_user_id: str | None = None
) -> dict[str, Any]:
    async with _scheduler_tick_lock:
        return await _run_due_schedules_unlocked(db, now=now, actor_user_id=actor_user_id)


async def run_schedule_now(
    db: AsyncSession,
    *,
    org_id: str,
    schedule_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Run one schedule immediately (manual run / retry of a failed sync).

    Unlike :func:`run_due_schedules` this ignores ``next_run_at``: the schedule
    is synced right away and its ``last_run_at`` / ``next_run_at`` are advanced
    as usual. The sync runs with ``trigger="manual"`` so the metrics label
    distinguishes an on-demand run from the cron-driven path.
    """
    correlation_id = gen_id()
    schedule = await CiScheduleRepository(db).get(org_id, schedule_id)
    if schedule is None:
        raise KeyError("schedule not found")
    synced, cases = await _run_one(
        db,
        schedule,
        now=utc_now(),
        actor_user_id=actor_user_id,
        trigger="manual",
        correlation_id=correlation_id,
    )
    return {
        "schedule_id": schedule_id,
        "connection_id": schedule.connection_id,
        "synced": synced,
        "new_cases": cases,
        "correlation_id": correlation_id,
    }


async def _run_one(
    db: AsyncSession,
    schedule: CiSchedule,
    *,
    now: datetime,
    actor_user_id: str | None,
    trigger: str = "scheduled",
    correlation_id: str | None = None,
) -> tuple[int, int]:
    """Sync a single schedule and advance its next run."""
    if not schedule.enabled:
        raise IngestionError("schedule disabled")

    correlation_id = correlation_id or gen_id()
    result = await sync_connection(
        db,
        org_id=schedule.org_id,
        connection_id=schedule.connection_id,
        trigger=trigger,
        max_messages=SCHEDULED_MAX_MESSAGES,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    next_run = compute_next_run_at(schedule.run_time, schedule.timezone, now=now)
    await CiScheduleRepository(db).update(schedule, {"last_run_at": now, "next_run_at": next_run})
    await log_action(
        db,
        org_id=schedule.org_id,
        actor_user_id=actor_user_id,
        action="ci.schedule.ran",
        resource_type="ci_schedule",
        resource_id=schedule.id,
        metadata={
            "connection_id": schedule.connection_id,
            "trigger": trigger,
            "synced": result.get("synced", 0),
            "new_cases": result.get("new_cases", 0),
            "correlation_id": correlation_id,
        },
    )

    synced = result.get("synced", 0)
    cases = result.get("new_cases", 0)
    await logger.ainfo(
        "ci_scheduled_sync_done",
        schedule_id=schedule.id,
        synced=synced,
        new_cases=cases,
        next_run_at=next_run.isoformat(),
        correlation_id=correlation_id,
    )
    return synced, cases