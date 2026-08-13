from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.customer_intelligence.scheduler import enqueue_gmail_maintenance_events
from app.db.base import Base
from app.models.customer_intelligence import EmailConnection
from app.models.organization import Organization
from app.models.outbox import OutboxEvent


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_gmail_maintenance_fanout_is_entity_deduplicated(async_session_factory):
    async with async_session_factory() as db:
        db.add(Organization(id="org-maint", name="Maintenance", slug="maintenance"))
        db.add(
            EmailConnection(
                id="conn-maint",
                org_id="org-maint",
                provider="gmail",
                account_email="maint@example.com",
                status="connected",
            )
        )
        await db.commit()
        first = await enqueue_gmail_maintenance_events(db)
        second = await enqueue_gmail_maintenance_events(db)
        events = list((await db.scalars(select(OutboxEvent))).all())

        assert first["connections"] == 1
        assert second["connections"] == 1
        assert len(events) == 1
        assert events[0].event_type == "gmail.reconciliation.requested"
