from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.job_schedule import JobScheduleExecution


class JobScheduleExecutionRepository:
    """Persistence boundary for generic scheduled-job leases."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def try_claim(
        self,
        *,
        job_key: str,
        scheduled_for: datetime,
        lease_owner: str,
        lease_seconds: int,
    ) -> JobScheduleExecution | None:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        existing = await self._get_for_update(job_key, scheduled_for)
        if existing is not None:
            if existing.status in {"succeeded", "failed"}:
                return None
            if existing.lease_expires_at > now:
                return None
            existing.lease_owner = lease_owner
            existing.lease_expires_at = lease_expires_at
            existing.status = "running"
            existing.attempt += 1
            existing.started_at = now
            existing.finished_at = None
            existing.error = None
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        execution = JobScheduleExecution(
            job_key=job_key,
            scheduled_for=scheduled_for,
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
            status="running",
            attempt=1,
            started_at=now,
        )
        try:
            # The SAVEPOINT keeps a duplicate-key race from poisoning an
            # outer AsyncSession transaction on both SQLite and PostgreSQL.
            async with self.db.begin_nested():
                self.db.add(execution)
                await self.db.flush()
        except IntegrityError:
            winner = await self._get_for_update(job_key, scheduled_for)
            if winner is None:
                return None
            if winner.status == "running" and winner.lease_expires_at > utc_now():
                return None
            return await self.try_claim(
                job_key=job_key,
                scheduled_for=scheduled_for,
                lease_owner=lease_owner,
                lease_seconds=lease_seconds,
            )
        await self.db.commit()
        await self.db.refresh(execution)
        return execution

    async def mark_succeeded(self, execution: JobScheduleExecution, *, result_summary: dict) -> None:
        execution.status = "succeeded"
        execution.result_summary = result_summary
        execution.error = None
        execution.finished_at = utc_now()
        await self.db.commit()

    async def mark_failed(self, execution: JobScheduleExecution, *, error: str) -> None:
        execution.status = "failed"
        execution.error = error[:4000]
        execution.finished_at = utc_now()
        await self.db.commit()

    async def _get_for_update(
        self, job_key: str, scheduled_for: datetime
    ) -> JobScheduleExecution | None:
        statement = select(JobScheduleExecution).where(
            JobScheduleExecution.job_key == job_key,
            JobScheduleExecution.scheduled_for == scheduled_for,
        )
        # SQLite ignores FOR UPDATE; PostgreSQL locks the existing row.
        statement = statement.with_for_update()
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()
