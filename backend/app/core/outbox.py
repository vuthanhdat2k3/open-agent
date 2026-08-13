from __future__ import annotations

from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workflow.queue import enqueue_outbox_event
from app.db.base import utc_now
from app.repositories.outbox import OutboxRepository


async def publish_pending_outbox(
    db: AsyncSession, *, owner: str, limit: int = 100
) -> dict[str, int]:
    """Publish leased DB events; Redis failure leaves them retryable in Postgres."""
    repo = OutboxRepository(db)
    events = await repo.claim_batch(owner=owner, limit=limit)
    published = 0
    failed = 0
    for event in events:
        try:
            await enqueue_outbox_event(event.id)
            await repo.mark_published(event.id)
            published += 1
        except Exception as exc:  # noqa: BLE001 - retry is persisted below.
            await repo.mark_failed(
                event.id,
                error_code="queue_publish_failed",
                error=str(exc),
                retry_at=utc_now() + timedelta(seconds=30),
            )
            failed += 1
    return {"claimed": len(events), "published": published, "failed": failed}
