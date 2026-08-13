from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import pytest

from app.customer_intelligence.cutover import clean_cutover
from app.db.base import utc_now
from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import (
    BriefingReport,
    CiNotification,
    DeliveryAttempt,
    InboundEmail,
    Meeting,
    ResearchCase,
    ResearchSource,
)


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_clean_cutover_preserves_email_and_removes_derived_data(async_session_factory):
    async with async_session_factory() as session:
        email = InboundEmail(
            org_id="org-cutover",
            provider="gmail",
            provider_message_id="old-1",
            sender_email="old@sender.example",
            sender_domain="sender.example",
            subject="Old mail",
            body_text="old",
            received_at=utc_now(),
        )
        session.add(email)
        await session.flush()
        case = ResearchCase(org_id="org-cutover", email_id=email.id, status="REPORT_READY")
        session.add(case)
        await session.flush()
        session.add_all(
            [
                BriefingReport(org_id="org-cutover", case_id=case.id, version=1),
                ResearchSource(org_id="org-cutover", case_id=case.id, url="https://example.com", source_type="website"),
                Meeting(org_id="org-cutover", case_id=case.id, provider_event_id="event-1", match_type="possible_match"),
                CiNotification(org_id="org-cutover", user_id="user-1", email_id=email.id, notification_type="email_received", title="old"),
                ApprovalRequest(org_id="org-cutover", case_id=case.id, run_type="ci", status="pending", idempotency_key="old-approval"),
                DeliveryAttempt(org_id="org-cutover", case_id=case.id, action="save_knowledge", payload_hash="x", idempotency_key="old-delivery"),
            ]
        )
        await session.commit()

        result = await clean_cutover(session, org_id="org-cutover", actor="test")
        assert result["marked_emails"] == 1
        assert result["deleted_cases"] == 1

        saved_email = (await session.execute(select(InboundEmail))).scalar_one()
        assert saved_email.classification == "historical_skipped"
        assert saved_email.routing_status == "historical_skipped"
        assert not (await session.execute(select(ResearchCase))).scalars().all()
        assert not (await session.execute(select(BriefingReport))).scalars().all()
        assert not (await session.execute(select(ApprovalRequest))).scalars().all()
