from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.scheduling.backoff import compute_backoff_seconds
from app.core.scheduling.tick import run_leased_tick
from app.db.base import Base, utc_now
from app.models.customer_intelligence import EmailConnection, InboundEmail, ResearchCase
from app.models.job_schedule import JobScheduleExecution
from app.models.organization import Organization
from app.repositories.customer_intelligence import ResearchCaseRepository
from app.repositories.job_schedule import JobScheduleExecutionRepository


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


def test_backoff_is_bounded_and_non_negative() -> None:
    for retry_count in range(8):
        value = compute_backoff_seconds(retry_count, base=10, cap=30)
        assert 0 <= value <= 30


@pytest.mark.asyncio
async def test_schedule_claim_is_unique_and_expired_claim_is_recoverable(async_session_factory):
    scheduled_for = utc_now().replace(second=0, microsecond=0)
    async with async_session_factory() as session:
        repo = JobScheduleExecutionRepository(session)
        first = await repo.try_claim(
            job_key="ci_scheduler_tick",
            scheduled_for=scheduled_for,
            lease_owner="worker-a",
            lease_seconds=60,
        )
        second = await repo.try_claim(
            job_key="ci_scheduler_tick",
            scheduled_for=scheduled_for,
            lease_owner="worker-b",
            lease_seconds=60,
        )
        assert first is not None
        assert second is None

        first.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()
        recovered = await repo.try_claim(
            job_key="ci_scheduler_tick",
            scheduled_for=scheduled_for,
            lease_owner="worker-b",
            lease_seconds=60,
        )
        assert recovered is not None
        assert recovered.id == first.id
        assert recovered.lease_owner == "worker-b"
        assert recovered.attempt == 2


@pytest.mark.asyncio
async def test_leased_tick_skips_second_runner(async_session_factory):
    calls = 0

    async def run() -> dict:
        nonlocal calls
        calls += 1
        return {"processed": 1}

    async with async_session_factory() as session:
        await run_leased_tick(
            session,
            job_key="test_tick",
            interval_seconds=60,
            lease_seconds=30,
            worker_id="worker-a",
            run=run,
        )
        await run_leased_tick(
            session,
            job_key="test_tick",
            interval_seconds=60,
            lease_seconds=30,
            worker_id="worker-b",
            run=run,
        )

    assert calls == 1


@pytest.mark.asyncio
async def test_research_case_retry_is_due_and_records_manual_actor(async_session_factory):
    now = utc_now()
    async with async_session_factory() as session:
        org = Organization(id="org-retry-test", name="Retry Org", slug="retry-org")
        connection = EmailConnection(
            id="conn-retry-test",
            org_id=org.id,
            provider="gmail",
            account_email="retry@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-retry-test",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-retry-test",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-retry-test",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="RESEARCHING",
        )
        session.add_all([org, connection, email, case])
        await session.commit()

        repository = ResearchCaseRepository(session)
        updated = await repository.schedule_retry(
            case,
            next_retry_at=now - timedelta(seconds=1),
            triggered_by="user-retry-test",
        )
        assert updated.status == "RETRYING"
        assert updated.retry_count == 1
        assert updated.last_retry_triggered_by == "user-retry-test"

        due = await repository.list_due_for_retry(now)
        assert [item.id for item in due] == [case.id]

        row = (
            await session.execute(
                select(JobScheduleExecution).where(JobScheduleExecution.job_key == "missing")
            )
        ).scalar_one_or_none()
        assert row is None



@pytest.mark.asyncio
async def test_research_failure_is_scheduled_for_retry(async_session_factory, monkeypatch):
    now = utc_now()
    async with async_session_factory() as session:
        org = Organization(id="org-research-fail", name="Research Fail", slug="research-fail")
        connection = EmailConnection(
            id="conn-research-fail",
            org_id=org.id,
            provider="gmail",
            account_email="research@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-research-fail",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-research-fail",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-research-fail",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="INGESTED",
        )
        session.add_all([org, connection, email, case])
        await session.commit()

        async def fail_after_entering_research(db, *, org_id, case_id, actor_user_id=None):
            current = await ResearchCaseRepository(db).get(org_id, case_id)
            current.status = "RESEARCHING"
            await db.commit()
            raise RuntimeError("provider timeout")

        monkeypatch.setattr("app.customer_intelligence.workflow.run_research", fail_after_entering_research)
        from app.services.customer_intelligence_service import CustomerIntelligenceService

        with pytest.raises(RuntimeError, match="provider timeout"):
            await CustomerIntelligenceService(session).research_case(
                org_id=org.id,
                case_id=case.id,
            )

        refreshed = await ResearchCaseRepository(session).get(org.id, case.id)
        assert refreshed.status == "RETRYING"
        assert refreshed.retry_count == 1
        assert refreshed.next_retry_at is not None


@pytest.mark.asyncio
async def test_due_research_retry_can_complete(async_session_factory, monkeypatch):
    now = utc_now()
    async with async_session_factory() as session:
        org = Organization(id="org-retry-complete", name="Retry Complete", slug="retry-complete")
        connection = EmailConnection(
            id="conn-retry-complete",
            org_id=org.id,
            provider="gmail",
            account_email="complete@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-retry-complete",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-retry-complete",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-retry-complete",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="RETRYING",
            retry_count=1,
            next_retry_at=now - timedelta(seconds=1),
        )
        session.add_all([org, connection, email, case])
        await session.commit()

        async def succeed_research(self, *, org_id, case_id, actor_user_id=None):
            current = await ResearchCaseRepository(self.db).get(org_id, case_id)
            current.status = "REPORT_READY"
            current.next_retry_at = None
            await self.db.commit()
            return {"case_id": case_id, "sources": 0, "meetings": 0}

        monkeypatch.setattr(
            "app.services.customer_intelligence_service.CustomerIntelligenceService.research_case",
            succeed_research,
        )
        from app.customer_intelligence.scheduler import process_due_retries

        result = await process_due_retries(session)
        refreshed = await ResearchCaseRepository(session).get(org.id, case.id)
        assert result["retried"] == 1
        assert refreshed.status == "REPORT_READY"



@pytest.mark.asyncio
async def test_manual_retry_reopens_dead_letter_and_records_actor(async_session_factory):
    now = utc_now()
    async with async_session_factory() as session:
        org = Organization(id="org-manual-retry", name="Manual Retry", slug="manual-retry")
        connection = EmailConnection(
            id="conn-manual-retry",
            org_id=org.id,
            provider="gmail",
            account_email="manual@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-manual-retry",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-manual-retry",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-manual-retry",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="DEAD_LETTER",
            retry_count=5,
        )
        session.add_all([org, connection, email, case])
        await session.commit()

        from app.services.customer_intelligence_service import CustomerIntelligenceService

        updated = await CustomerIntelligenceService(session).retry_case(
            org_id=org.id,
            case_id=case.id,
            actor_user_id="manual-operator",
        )
        assert updated.status == "RETRYING"
        assert updated.retry_count == 6
        assert updated.last_retry_triggered_by == "manual-operator"
        assert updated.next_retry_at is not None


@pytest.mark.asyncio
async def test_failed_tick_is_not_reclaimed_for_same_schedule_slot(async_session_factory):
    calls = 0

    async def fail() -> dict:
        nonlocal calls
        calls += 1
        raise RuntimeError("temporary tick failure")

    scheduled_for = utc_now().replace(second=0, microsecond=0)
    async with async_session_factory() as session:
        # The helper derives the slot from utc_now; using the same minute makes
        # both invocations address the same durable execution row.
        await run_leased_tick(
            session,
            job_key="failed_tick",
            interval_seconds=60,
            lease_seconds=30,
            worker_id="worker-a",
            run=fail,
        )
        await run_leased_tick(
            session,
            job_key="failed_tick",
            interval_seconds=60,
            lease_seconds=30,
            worker_id="worker-b",
            run=fail,
        )
        row = (
            await session.execute(
                select(JobScheduleExecution).where(JobScheduleExecution.job_key == "failed_tick")
            )
        ).scalar_one()

    assert calls == 1
    assert row.status == "failed"
    assert row.error == "temporary tick failure"


@pytest.mark.asyncio
async def test_non_transient_research_error_dead_letters_due_case(async_session_factory, monkeypatch):
    now = utc_now()
    async with async_session_factory() as session:
        org = Organization(id="org-hard-retry", name="Hard Retry", slug="hard-retry")
        connection = EmailConnection(
            id="conn-hard-retry",
            org_id=org.id,
            provider="gmail",
            account_email="hard@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-hard-retry",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-hard-retry",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-hard-retry",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="RETRYING",
            retry_count=1,
            next_retry_at=now - timedelta(seconds=1),
        )
        session.add_all([org, connection, email, case])
        await session.commit()

        async def reject_research(self, *, org_id, case_id, actor_user_id=None):
            from app.customer_intelligence.workflow import ResearchError

            raise ResearchError("case email not found")

        monkeypatch.setattr(
            "app.services.customer_intelligence_service.CustomerIntelligenceService.research_case",
            reject_research,
        )
        from app.customer_intelligence.scheduler import process_due_retries

        result = await process_due_retries(session)
        refreshed = await ResearchCaseRepository(session).get(org.id, case.id)

    assert result["dead_lettered"] == 1
    assert refreshed.status == "DEAD_LETTER"
    assert refreshed.error == "case email not found"



@pytest.mark.asyncio
async def test_due_delivery_retry_completes_via_run_delivery(async_session_factory, monkeypatch):
    now = utc_now()
    from app.models.approval_request import ApprovalRequest
    from app.models.customer_intelligence import BriefingReport

    async with async_session_factory() as session:
        org = Organization(id="org-delivery-retry", name="Delivery Retry", slug="delivery-retry")
        connection = EmailConnection(
            id="conn-delivery-retry",
            org_id=org.id,
            provider="gmail",
            account_email="delivery@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-delivery-retry",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-delivery-retry",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-delivery-retry",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="RETRYING",
            retry_count=1,
            next_retry_at=now - timedelta(seconds=1),
        )
        report = BriefingReport(
            id="report-delivery-retry",
            org_id=org.id,
            case_id=case.id,
            version=1,
            canonical_markdown="# Acme briefing",
            status="ready",
        )
        approval = ApprovalRequest(
            id="approval-delivery-retry",
            org_id=org.id,
            run_type="ci.delivery",
            run_id=case.id,
            tool_name="send_email",
            case_id=case.id,
            status="approved",
            decided_at=now,
            args_snapshot={"to": "sales@acme.com", "subject": "Briefing", "body": "hi"},
            idempotency_key=f"ci:{case.id}:send_email",
        )
        session.add_all([org, connection, email, case, report, approval])
        await session.commit()

        called = {}

        async def fake_run_delivery(db, *, org_id, case, approval, actor_user_id=None):
            called["case_id"] = case.id
            called["approval_id"] = approval.id
            from app.models.customer_intelligence import DeliveryAttempt

            attempt = DeliveryAttempt(
                org_id=org_id,
                case_id=case.id,
                action="send_email",
                payload_hash="test-hash",
                idempotency_key=approval.idempotency_key,
                status="delivered",
            )
            db.add(attempt)
            await db.commit()
            return attempt

        monkeypatch.setattr(
            "app.customer_intelligence.delivery.run_delivery", fake_run_delivery
        )
        from app.customer_intelligence.scheduler import process_due_retries

        result = await process_due_retries(session)
        refreshed = await ResearchCaseRepository(session).get(org.id, case.id)

    assert result["retried"] == 1
    assert result["dead_lettered"] == 0
    assert called["case_id"] == case.id
    assert called["approval_id"] == approval.id
    assert refreshed.status == "COMPLETED"


@pytest.mark.asyncio
async def test_due_delivery_retry_without_approval_dead_letters_immediately(
    async_session_factory,
):
    now = utc_now()
    from app.models.customer_intelligence import BriefingReport

    async with async_session_factory() as session:
        org = Organization(id="org-delivery-no-approval", name="No Approval", slug="no-approval")
        connection = EmailConnection(
            id="conn-delivery-no-approval",
            org_id=org.id,
            provider="gmail",
            account_email="noapproval@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-delivery-no-approval",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-delivery-no-approval",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-delivery-no-approval",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="RETRYING",
            retry_count=1,
            next_retry_at=now - timedelta(seconds=1),
        )
        report = BriefingReport(
            id="report-delivery-no-approval",
            org_id=org.id,
            case_id=case.id,
            version=1,
            canonical_markdown="# Acme briefing",
            status="ready",
        )
        # No ApprovalRequest at all: this is a permanent configuration problem
        # (the approval was never granted), not a transient failure.
        session.add_all([org, connection, email, case, report])
        await session.commit()

        from app.customer_intelligence.scheduler import process_due_retries

        result = await process_due_retries(session)
        refreshed = await ResearchCaseRepository(session).get(org.id, case.id)

    # A missing approval must not consume all 5 retries before dead-lettering.
    assert result["dead_lettered"] == 1
    assert result["retried"] == 0
    assert refreshed.status == "DEAD_LETTER"
    assert refreshed.retry_count == 1
    assert "approved delivery request not found" in (refreshed.error or "")


@pytest.mark.asyncio
async def test_process_due_retries_dead_letters_after_max_retry_count(
    async_session_factory, monkeypatch
):
    now = utc_now()
    async with async_session_factory() as session:
        org = Organization(id="org-max-retry", name="Max Retry", slug="max-retry")
        connection = EmailConnection(
            id="conn-max-retry",
            org_id=org.id,
            provider="gmail",
            account_email="maxretry@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-max-retry",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-max-retry",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-max-retry",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="RETRYING",
            retry_count=5,
            next_retry_at=now - timedelta(seconds=1),
        )
        session.add_all([org, connection, email, case])
        await session.commit()

        async def raise_generic(self, *, org_id, case_id, actor_user_id=None):
            # A generic (non-ResearchError) exception that is NOT recorded as
            # a fresh retry by the service itself, to isolate the
            # process_due_retries MAX_RETRY_COUNT branch.
            raise RuntimeError("provider still unavailable")

        monkeypatch.setattr(
            "app.services.customer_intelligence_service.CustomerIntelligenceService.research_case",
            raise_generic,
        )
        from app.customer_intelligence.scheduler import process_due_retries

        org_id, case_id = org.id, case.id
        result = await process_due_retries(session)
        refreshed = await ResearchCaseRepository(session).get(org_id, case_id)

    assert result["dead_lettered"] == 1
    assert refreshed.status == "DEAD_LETTER"
    assert refreshed.error == "customer intelligence retry limit exceeded"


@pytest.mark.asyncio
async def test_manual_retry_from_retrying_status_reschedules_without_transition(
    async_session_factory,
):
    now = utc_now()
    async with async_session_factory() as session:
        org = Organization(id="org-manual-retrying", name="Manual Retrying", slug="manual-retrying")
        connection = EmailConnection(
            id="conn-manual-retrying",
            org_id=org.id,
            provider="gmail",
            account_email="manualretrying@example.com",
            status="connected",
        )
        email = InboundEmail(
            id="email-manual-retrying",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="provider-manual-retrying",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        case = ResearchCase(
            id="case-manual-retrying",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            status="RETRYING",
            retry_count=2,
            next_retry_at=now + timedelta(minutes=10),
        )
        session.add_all([org, connection, email, case])
        await session.commit()

        from app.services.customer_intelligence_service import CustomerIntelligenceService

        updated = await CustomerIntelligenceService(session).retry_case(
            org_id=org.id,
            case_id=case.id,
            actor_user_id="manual-operator-2",
        )

    assert updated.status == "RETRYING"
    assert updated.retry_count == 3
    assert updated.last_retry_triggered_by == "manual-operator-2"
    # Manual retry must bring the next attempt forward to "now", not leave
    # the case waiting out its previous backoff window.
    assert updated.next_retry_at <= utc_now()

