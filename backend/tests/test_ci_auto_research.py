"""Tests for durable async classification and downstream research jobs."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.customer_intelligence.ingest import sync_connection
from app.customer_intelligence.mcp import CustomerIntelligenceMcpError
from app.customer_intelligence.security import encrypt_credentials
from app.customer_intelligence.workflow import _unverified_company_candidate
from app.db.base import Base, utc_now
from app.models.customer_intelligence import EmailConnection, InboundEmail, ResearchCase
from app.models.outbox import OutboxEvent
from app.repositories.customer_intelligence import ResearchCaseRepository


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


def test_unverified_company_candidate_keeps_research_available() -> None:
    case = ResearchCase(company_name="Acme Example Corporation", company_domain="acme.example")

    candidate = _unverified_company_candidate(case)

    assert candidate is not None
    assert candidate.canonical_name == "Acme Example Corporation"
    assert candidate.domain == "acme.example"
    assert candidate.source == "agent-classifier-unverified"


async def _seed_connection(async_session_factory, org_id: str) -> str:
    async with async_session_factory() as session:
        conn = EmailConnection(
            org_id=org_id,
            provider="gmail",
            account_email="fake@example.com",
            status="connected",
            credentials_enc=encrypt_credentials({"access_token": "test"}),
        )
        session.add(conn)
        await session.commit()
        return conn.id


async def test_sync_persists_classification_outbox_for_each_new_email(
    async_session_factory, ci_mcp_stub
):
    org_id = "org-autoresearch-clean"
    conn_id = await _seed_connection(async_session_factory, org_id)

    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="manual"
        )
        assert result["new_cases"] == 0
        assert result["classification_queued"] == 1
        event = (await session.execute(select(OutboxEvent))).scalar_one()
        assert event.event_type == "email.classification.requested"
        assert event.org_id == org_id


def _mail(message_id: str) -> dict:
    return {
        "provider": "gmail",
        "provider_message_id": message_id,
        "thread_id": None,
        "sender_name": "Sales",
        "sender_email": "sales@acme.example",
        "sender_domain": "acme.example",
        "recipients": ["user@example.com"],
        "subject": "Customer request",
        "body_text": "Please send a quote.",
        "body_html": None,
        "attachments": [],
        "received_at": "2026-08-06T00:00:00+00:00",
        "headers": {},
    }


async def test_reconciliation_uses_history_checkpoint_not_messages_cursor(
    async_session_factory, monkeypatch
):
    org_id = "org-history-incremental"
    conn_id = await _seed_connection(async_session_factory, org_id)
    async with async_session_factory() as session:
        conn = await session.get(EmailConnection, conn_id)
        conn.gmail_history_id = "h0"
        conn.sync_cursor = {"cursor": "stale-page-token"}
        await session.commit()

    calls: list[str] = []

    async def call(tool: str, args: dict):
        calls.append(tool)
        if tool == "email_history":
            return {
                "messages": [_mail("delta-1")],
                "new_cursor": None,
                "history_id": "h1",
                "has_more": False,
            }
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(
        "app.customer_intelligence.providers.email.call_customer_intelligence_mcp", call
    )
    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="reconciliation"
        )
        refreshed = await session.get(EmailConnection, conn_id)

    assert calls == ["email_history"]
    assert result["mode"] == "history"
    assert refreshed.gmail_history_id == "h1"
    assert refreshed.sync_cursor is None


async def test_expired_history_performs_bounded_recovery_and_reseeds_checkpoint(
    async_session_factory, monkeypatch
):
    org_id = "org-history-recovery"
    conn_id = await _seed_connection(async_session_factory, org_id)
    async with async_session_factory() as session:
        conn = await session.get(EmailConnection, conn_id)
        conn.gmail_history_id = "expired"
        await session.commit()

    calls: list[str] = []

    async def call(tool: str, args: dict):
        calls.append(tool)
        if tool == "email_history":
            raise CustomerIntelligenceMcpError("history_expired: checkpoint unavailable")
        if tool == "email_history_checkpoint":
            return {"history_id": "recovery-baseline"}
        if tool == "email_list_new":
            return {"messages": [_mail("recovered-1")], "new_cursor": None, "has_more": False}
        raise AssertionError(f"unexpected tool {tool}")

    monkeypatch.setattr(
        "app.customer_intelligence.providers.email.call_customer_intelligence_mcp", call
    )
    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="reconciliation"
        )
        refreshed = await session.get(EmailConnection, conn_id)

    assert calls == ["email_history", "email_history_checkpoint", "email_list_new"]
    assert result["mode"] == "bootstrap"
    assert any("expired" in warning for warning in result["warnings"])
    assert refreshed.gmail_history_id == "recovery-baseline"


async def test_sync_scopes_email_and_event_to_connection_owner(async_session_factory, ci_mcp_stub):
    org_id = "org-autoresearch-owner"
    owner_id = "user-owner"
    conn_id = await _seed_connection(async_session_factory, org_id)
    async with async_session_factory() as session:
        connection = await session.get(EmailConnection, conn_id)
        connection.created_by_user_id = owner_id
        await session.commit()

    async with async_session_factory() as session:
        await sync_connection(session, org_id=org_id, connection_id=conn_id)

    async with async_session_factory() as session:
        email = (await session.execute(select(InboundEmail))).scalar_one()
        event = (await session.execute(select(OutboxEvent))).scalar_one()

    assert email.created_by_user_id == owner_id
    assert event.user_id == owner_id


async def test_sync_keeps_guard_flags_as_classification_context(
    async_session_factory, ci_mcp_stub, monkeypatch
):
    org_id = "org-autoresearch-flagged"
    conn_id = await _seed_connection(async_session_factory, org_id)

    def fake_scan(_body: str) -> list[str]:
        return ["prompt_injection"]

    monkeypatch.setattr("app.customer_intelligence.ingest.scan_for_prompt_injection", fake_scan)

    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="manual"
        )
        assert result["synced"] == 1
        assert result["new_cases"] == 0
        email = (await session.execute(select(InboundEmail))).scalar_one()
        assert email.injection_flags == ["prompt_injection"]
        assert (await session.execute(select(OutboxEvent))).scalar_one()


async def test_sync_does_not_depend_on_live_redis(async_session_factory, ci_mcp_stub):
    org_id = "org-autoresearch-queue-down"
    conn_id = await _seed_connection(async_session_factory, org_id)

    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="manual"
        )
        assert result["classification_queued"] == 1


async def test_run_ci_research_calls_research_for_ingested_case(async_session_factory, monkeypatch):
    from app.customer_intelligence.jobs import run_ci_research

    now = utc_now()
    async with async_session_factory() as session:
        conn = EmailConnection(
            org_id="org-job-ingested",
            provider="gmail",
            account_email="job@example.com",
            status="connected",
        )
        session.add(conn)
        await session.flush()
        email = InboundEmail(
            org_id="org-job-ingested",
            connection_id=conn.id,
            provider="gmail",
            provider_message_id="job-msg-1",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        session.add(email)
        await session.flush()
        case = ResearchCase(
            org_id="org-job-ingested",
            email_id=email.id,
            connection_id=conn.id,
            status="INGESTED",
        )
        session.add(case)
        await session.commit()
        case_id = case.id

    called = {}

    async def fake_run_research(db, *, org_id, case_id, actor_user_id=None):
        called["org_id"] = org_id
        called["case_id"] = case_id
        return {"case_id": case_id}

    monkeypatch.setattr("app.customer_intelligence.workflow.run_research", fake_run_research)
    monkeypatch.setattr("app.customer_intelligence.jobs.SessionLocal", async_session_factory)

    await run_ci_research({"job_try": 1}, "org-job-ingested", case_id)

    assert called == {"org_id": "org-job-ingested", "case_id": case_id}


async def test_run_ci_research_skips_case_already_past_ingested(async_session_factory, monkeypatch):
    from app.customer_intelligence.jobs import run_ci_research

    now = utc_now()
    async with async_session_factory() as session:
        conn = EmailConnection(
            org_id="org-job-skip",
            provider="gmail",
            account_email="skip@example.com",
            status="connected",
        )
        session.add(conn)
        await session.flush()
        email = InboundEmail(
            org_id="org-job-skip",
            connection_id=conn.id,
            provider="gmail",
            provider_message_id="job-msg-skip",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        session.add(email)
        await session.flush()
        # Already researched via the manual API before the enqueued job runs.
        case = ResearchCase(
            org_id="org-job-skip",
            email_id=email.id,
            connection_id=conn.id,
            status="REPORT_READY",
        )
        session.add(case)
        await session.commit()
        case_id = case.id

    called = {"count": 0}

    async def fake_run_research(db, *, org_id, case_id, actor_user_id=None):
        called["count"] += 1
        return {}

    monkeypatch.setattr("app.customer_intelligence.workflow.run_research", fake_run_research)
    monkeypatch.setattr("app.customer_intelligence.jobs.SessionLocal", async_session_factory)

    await run_ci_research({"job_try": 1}, "org-job-skip", case_id)

    assert called["count"] == 0

    refreshed = None
    async with async_session_factory() as session:
        refreshed = await ResearchCaseRepository(session).get("org-job-skip", case_id)
    assert refreshed.status == "REPORT_READY"


async def test_run_ci_research_retries_transient_failure(async_session_factory, monkeypatch):
    from app.customer_intelligence.jobs import run_ci_research

    now = utc_now()
    async with async_session_factory() as session:
        conn = EmailConnection(
            org_id="org-job-retry",
            provider="gmail",
            account_email="retry@example.com",
            status="connected",
        )
        session.add(conn)
        await session.flush()
        email = InboundEmail(
            org_id="org-job-retry",
            connection_id=conn.id,
            provider="gmail",
            provider_message_id="job-msg-retry",
            sender_email="sender@example.com",
            sender_domain="example.com",
            received_at=now,
        )
        session.add(email)
        await session.flush()
        case = ResearchCase(
            org_id="org-job-retry",
            email_id=email.id,
            connection_id=conn.id,
            status="INGESTED",
        )
        session.add(case)
        await session.commit()
        case_id = case.id

    async def failing_run_research(db, *, org_id, case_id, actor_user_id=None):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr("app.customer_intelligence.workflow.run_research", failing_run_research)
    monkeypatch.setattr("app.customer_intelligence.jobs.SessionLocal", async_session_factory)

    await run_ci_research({"job_try": 1}, "org-job-retry", case_id)

    async with async_session_factory() as session:
        refreshed = await ResearchCaseRepository(session).get("org-job-retry", case_id)
    assert refreshed.status == "RETRYING"
    assert refreshed.retry_count == 1

    # A duplicate message while backoff is pending is a safe no-op.
    await run_ci_research({"job_try": 3}, "org-job-retry", case_id)
