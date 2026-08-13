from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.metrics import job_schedule_tick_total
from app.db.base import utc_now
from app.repositories.job_schedule import JobScheduleExecutionRepository

logger = structlog.get_logger(__name__)


def round_down_to_interval(now: datetime, interval_seconds: int) -> datetime:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    aware = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    epoch_seconds = int(aware.timestamp())
    floored = epoch_seconds - (epoch_seconds % interval_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc).replace(tzinfo=None)


async def run_leased_tick(
    db: AsyncSession,
    *,
    job_key: str,
    interval_seconds: int,
    lease_seconds: int,
    worker_id: str,
    run: Callable[[], Awaitable[dict[str, Any]]],
) -> None:
    scheduled_for = round_down_to_interval(utc_now(), interval_seconds)
    repository = JobScheduleExecutionRepository(db)
    execution = await repository.try_claim(
        job_key=job_key,
        scheduled_for=scheduled_for,
        lease_owner=worker_id,
        lease_seconds=lease_seconds,
    )
    if execution is None:
        job_schedule_tick_total.labels(job_key=job_key, result="skipped_lease_held").inc()
        await logger.adebug(
            "job_tick_skipped_lease_held",
            job_key=job_key,
            scheduled_for=scheduled_for.isoformat(),
        )
        return

    try:
        result = await run()
    except Exception as exc:  # noqa: BLE001 - record failure, keep ARQ alive.
        await repository.mark_failed(execution, error=str(exc))
        job_schedule_tick_total.labels(job_key=job_key, result="claimed_failed").inc()
        await logger.aerror("job_tick_failed", job_key=job_key, error=str(exc))
        return

    await repository.mark_succeeded(execution, result_summary=result or {})
    job_schedule_tick_total.labels(job_key=job_key, result="claimed_succeeded").inc()
