from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.outbox import OutboxEvent, ProcessedEvent


class OutboxRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_event(self, **values) -> OutboxEvent:
        """Add an event without committing; caller owns the business transaction."""
        dedupe_key = values.get("dedupe_key")
        if dedupe_key:
            existing = await self.db.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == values["event_type"],
                    OutboxEvent.dedupe_key == dedupe_key,
                )
            )
            if existing:
                return existing

        event = OutboxEvent(**values)
        self.db.add(event)
        try:
            async with self.db.begin_nested():
                await self.db.flush()
        except IntegrityError:
            # The unique constraint is the final race-safe dedupe guard.
            # begin_nested() already rolled back only its savepoint. Never
            # roll back the caller's business transaction here: an outbox
            # dedupe race must not erase the aggregate change that surrounds it.
            existing = await self.db.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == values["event_type"],
                    OutboxEvent.dedupe_key == dedupe_key,
                )
            )
            if existing is None:
                raise
            return existing
        return event

    async def claim_batch(
        self, *, owner: str, limit: int = 100, lease_seconds: int = 30
    ) -> list[OutboxEvent]:
        now = utc_now()
        rows = (
            await self.db.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.available_at <= now,
                    or_(
                        OutboxEvent.status == "pending",
                        OutboxEvent.status == "failed",
                        (OutboxEvent.status == "leased") & (OutboxEvent.lease_until < now),
                    ),
                )
                .order_by(OutboxEvent.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        until = now + timedelta(seconds=lease_seconds)
        for event in rows:
            event.status = "leased"
            event.lease_owner = owner
            event.lease_until = until
            event.attempt_count += 1
        await self.db.commit()
        return rows

    async def mark_published(self, event_id: str) -> None:
        event = await self.db.get(OutboxEvent, event_id)
        if event:
            event.status = "published"
            event.published_at = utc_now()
            event.lease_owner = None
            event.lease_until = None
            event.last_error = None
            await self.db.commit()

    async def mark_failed(self, event_id: str, *, error_code: str, error: str, retry_at: datetime) -> None:
        event = await self.db.get(OutboxEvent, event_id)
        if event:
            event.status = "failed"
            event.available_at = retry_at
            event.lease_owner = None
            event.lease_until = None
            event.last_error_code = error_code
            event.last_error = error[:2000]
            await self.db.commit()

    async def mark_processed(self, *, event_id: str, consumer_name: str) -> bool:
        existing = await self.db.scalar(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == event_id,
                ProcessedEvent.consumer_name == consumer_name,
            )
        )
        if existing:
            return False
        receipt = ProcessedEvent(event_id=event_id, consumer_name=consumer_name)
        self.db.add(receipt)
        try:
            async with self.db.begin_nested():
                await self.db.flush()
        except IntegrityError:
            # Keep the caller's transaction alive; the savepoint handled the
            # duplicate receipt race.
            return False
        return True
