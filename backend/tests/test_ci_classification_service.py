from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.customer_intelligence.classification_service import classify_and_route_email
from app.customer_intelligence.classifier import Classification
from app.db.base import Base, utc_now
from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import InboundEmail, ResearchCase
from app.models.outbox import OutboxEvent


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _email(session, *, org_id: str, message_id: str, flags: list[str] | None = None):
    row = InboundEmail(
        org_id=org_id,
        provider="gmail",
        provider_message_id=message_id,
        sender_email="sender@example.com",
        sender_domain="example.com",
        subject="Meeting request",
        body_text="Can we meet tomorrow?",
        received_at=utc_now(),
        content_hash=f"hash-{message_id}",
        injection_flags=flags or [],
        classification="queued",
    )
    session.add(row)
    await session.commit()
    return row


async def test_customer_classification_creates_research_case_and_outbox(
    async_session_factory, monkeypatch
):
    calls = 0

    async def classify(*_args):
        nonlocal calls
        calls += 1
        return Classification(
            "customer",
            0.96,
            "CUSTOMER_INTENT",
            company_name="Acme",
            company_domain="acme.example",
            company_confidence=0.93,
        )

    monkeypatch.setattr(
        "app.customer_intelligence.classification_service.classify_with_agent", classify
    )
    async with async_session_factory() as session:
        email = await _email(
            session, org_id="org-classify-customer", message_id="customer-1", flags=["possible"]
        )
        result = await classify_and_route_email(
            session,
            org_id=email.org_id,
            email_id=email.id,
            expected_content_hash=email.content_hash,
        )
        case = (await session.execute(select(ResearchCase))).scalar_one()
        event = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "ci.research.requested")
            )
        ).scalar_one()
        assert result["case_id"] == case.id
        assert case.status == "INGESTED"
        assert event.aggregate_id == case.id
        duplicate = await classify_and_route_email(
            session,
            org_id=email.org_id,
            email_id=email.id,
            expected_content_hash=email.content_hash,
        )
        assert duplicate["status"] == "already_processed"
        assert calls == 1


async def test_calendar_classification_creates_approval_without_company(
    async_session_factory, monkeypatch
):
    async def classify(*_args):
        return Classification(
            "calendar",
            0.97,
            "MEETING_REQUEST",
            meeting_confidence=0.95,
            calendar_payload={
                "start": "2026-08-15T03:00:00Z",
                "end": "2026-08-15T04:00:00Z",
                "timezone": "Asia/Bangkok",
                "attendees": ["sender@example.com"],
            },
        )

    monkeypatch.setattr(
        "app.customer_intelligence.classification_service.classify_with_agent", classify
    )
    async with async_session_factory() as session:
        email = await _email(session, org_id="org-classify-calendar", message_id="calendar-1")
        result = await classify_and_route_email(
            session, org_id=email.org_id, email_id=email.id
        )
        case = (await session.execute(select(ResearchCase))).scalar_one()
        approval = (await session.execute(select(ApprovalRequest))).scalar_one()
        assert result["case_id"] == case.id
        assert case.status == "AWAITING_APPROVAL"
        assert approval.tool_name == "calendar_create_event"
    async with async_session_factory() as fresh_session:
        persisted = (await fresh_session.execute(select(ApprovalRequest))).scalar_one()
        assert persisted.tool_name == "calendar_create_event"


async def test_customer_calendar_email_fans_out_research_and_calendar_data(
    async_session_factory, monkeypatch
):
    async def classify(*_args):
        return Classification(
            "customer",
            0.97,
            "CUSTOMER_AND_MEETING",
            company_name="Acme",
            company_domain="acme.example",
            company_confidence=0.93,
            meeting_confidence=0.95,
            intents=("request_briefing", "meeting_request"),
            calendar_payload={
                "start": "2026-08-15T03:00:00Z",
                "end": "2026-08-15T04:00:00Z",
                "timezone": "Asia/Bangkok",
                "attendees": ["sender@example.com"],
            },
        )

    monkeypatch.setattr(
        "app.customer_intelligence.classification_service.classify_with_agent", classify
    )
    async with async_session_factory() as session:
        email = await _email(session, org_id="org-classify-both", message_id="both-1")
        result = await classify_and_route_email(session, org_id=email.org_id, email_id=email.id)
        case = (await session.execute(select(ResearchCase))).scalar_one()
        event = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "ci.research.requested")
            )
        ).scalar_one()
        approvals = (await session.execute(select(ApprovalRequest))).scalars().all()
        assert result["case_id"] == case.id
        assert case.status == "INGESTED"
        assert event.aggregate_id == case.id
        assert approvals == []
