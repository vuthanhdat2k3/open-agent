from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.customer_intelligence.gmail_webhook import ingest_push
from app.db.base import Base
from app.models.customer_intelligence import EmailConnection, GmailNotification
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


def _push_body(email: str, history_id: str, message_id: str = "pubsub-1") -> dict:
    payload = base64.urlsafe_b64encode(
        json.dumps({"emailAddress": email, "historyId": history_id}).encode()
    ).decode()
    return {"message": {"data": payload, "messageId": message_id}}


@pytest.mark.asyncio
async def test_gmail_push_persists_and_deduplicates(async_session_factory):
    async with async_session_factory() as db:
        db.add(Organization(id="org-webhook", name="Webhook", slug="webhook"))
        db.add(
            EmailConnection(
                id="conn-webhook",
                org_id="org-webhook",
                provider="gmail",
                account_email="owner@example.com",
                status="connected",
            )
        )
        await db.commit()
        request = SimpleNamespace(headers={})

        first = await ingest_push(db, request, _push_body("owner@example.com", "100"))
        duplicate = await ingest_push(db, request, _push_body("owner@example.com", "100", "pubsub-2"))

        assert first == {"status": "accepted"}
        assert duplicate == {"status": "duplicate"}
        assert len((await db.scalars(select(GmailNotification))).all()) == 1
        event = await db.scalar(select(OutboxEvent))
        assert event is not None
        assert event.event_type == "gmail.history_sync.requested"
        assert event.dedupe_key == "gmail-history:conn-webhook:100"
