from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.outbox import publish_pending_outbox
from app.db.base import Base, utc_now
from app.models.organization import Organization
from app.models.outbox import OutboxEvent, ProcessedEvent
from app.repositories.outbox import OutboxRepository


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_dedupe_claim_and_consumer_receipt(async_session_factory):
    async with async_session_factory() as db:
        db.add(Organization(id="org-outbox", name="Outbox", slug="outbox"))
        await db.commit()
        repo = OutboxRepository(db)
        first = await repo.add_event(
            event_type="ci.research.requested",
            aggregate_type="research_case",
            aggregate_id="case-1",
            org_id="org-outbox",
            payload={"source": "gmail"},
            dedupe_key="case-1:1",
        )
        first_id = first.id
        second = await repo.add_event(
            event_type="ci.research.requested",
            aggregate_type="research_case",
            aggregate_id="case-1",
            org_id="org-outbox",
            payload={"source": "duplicate"},
            dedupe_key="case-1:1",
        )
        assert first.id == second.id
        await db.commit()

        claimed = await repo.claim_batch(owner="worker-a")
        assert [event.id for event in claimed] == [first_id]
        assert await repo.claim_batch(owner="worker-b") == []

        assert await repo.mark_processed(event_id=first_id, consumer_name="worker")
        assert not await repo.mark_processed(event_id=first_id, consumer_name="worker")
        await db.commit()

        receipt = await db.scalar(select(ProcessedEvent).where(ProcessedEvent.event_id == first_id))
        assert receipt is not None


@pytest.mark.asyncio
async def test_outbox_publish_failure_is_retryable(async_session_factory, monkeypatch):
    async with async_session_factory() as db:
        db.add(Organization(id="org-publish", name="Publish", slug="publish"))
        await db.commit()
        await OutboxRepository(db).add_event(
            event_type="ci.research.requested",
            aggregate_type="research_case",
            aggregate_id="case-publish",
            org_id="org-publish",
            payload={},
            dedupe_key="case-publish:1",
        )
        await db.commit()

        async def fail_enqueue(event_id: str, *, queue_name: str = "arq:queue") -> str:
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr("app.core.outbox.enqueue_outbox_event", fail_enqueue)
        result = await publish_pending_outbox(db, owner="worker-a")
        assert result == {"claimed": 1, "published": 0, "failed": 1}
        event = await db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == "case-publish"))
        assert event.status == "failed"
        assert event.available_at >= utc_now() + timedelta(seconds=29)
