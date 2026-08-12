"""Tests for auto-enqueuing CI research right after ingest creates a case.

``sync_connection`` used to leave every new case sitting in ``INGESTED``
forever unless someone called the research API by hand - these tests pin
down the fix: a clean new case gets a research job enqueued, a case flagged
for prompt injection never even gets created (so nothing is enqueued for
it), and the auto-research job itself only acts on cases still in a
researchable state and retries transient failures a bounded number of times.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.customer_intelligence.ingest import sync_connection
from app.customer_intelligence.security import encrypt_credentials
from app.db.base import Base, utc_now
from app.models.customer_intelligence import EmailConnection, InboundEmail, ResearchCase
from app.repositories.customer_intelligence import ResearchCaseRepository


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


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


async def test_sync_enqueues_research_for_each_new_clean_case(
    async_session_factory, ci_mcp_stub, monkeypatch
):
    org_id = "org-autoresearch-clean"
    conn_id = await _seed_connection(async_session_factory, org_id)

    enqueued: list[tuple[str, str]] = []

    async def fake_enqueue(org_id_arg: str, case_id_arg: str) -> str:
        enqueued.append((org_id_arg, case_id_arg))
        return "job-1"

    monkeypatch.setattr(
        "app.customer_intelligence.ingest.enqueue_ci_research", fake_enqueue
    )

    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="manual"
        )
        assert result["new_cases"] == 1

    assert len(enqueued) == 1
    assert enqueued[0][0] == org_id


async def test_sync_does_not_enqueue_for_flagged_email(
    async_session_factory, ci_mcp_stub, monkeypatch
):
    org_id = "org-autoresearch-flagged"
    conn_id = await _seed_connection(async_session_factory, org_id)

    # Force the sole synced email to look like a prompt-injection attempt so
    # ingest.py's own guard skips case creation - confirms no job is
    # enqueued when there is no case to research.
    def fake_scan(_body: str) -> list[str]:
        return ["prompt_injection"]

    monkeypatch.setattr(
        "app.customer_intelligence.ingest.scan_for_prompt_injection", fake_scan
    )

    enqueued: list[tuple[str, str]] = []

    async def fake_enqueue(org_id_arg: str, case_id_arg: str) -> str:
        enqueued.append((org_id_arg, case_id_arg))
        return "job-1"

    monkeypatch.setattr(
        "app.customer_intelligence.ingest.enqueue_ci_research", fake_enqueue
    )

    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="manual"
        )
        assert result["synced"] == 1
        assert result["new_cases"] == 0
        assert any("prompt injection" in w for w in result["warnings"])

    assert enqueued == []


async def test_sync_still_succeeds_when_enqueue_fails(
    async_session_factory, ci_mcp_stub, monkeypatch
):
    org_id = "org-autoresearch-queue-down"
    conn_id = await _seed_connection(async_session_factory, org_id)

    async def failing_enqueue(org_id_arg: str, case_id_arg: str) -> str:
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(
        "app.customer_intelligence.ingest.enqueue_ci_research", failing_enqueue
    )

    async with async_session_factory() as session:
        # Must not raise: a queue outage is not a sync failure, and the
        # case remains INGESTED for a manual research call or a later sweep.
        result = await sync_connection(
            session, org_id=org_id, connection_id=conn_id, trigger="manual"
        )
        assert result["new_cases"] == 1


async def test_run_ci_research_calls_research_for_ingested_case(
    async_session_factory, monkeypatch
):
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

    monkeypatch.setattr(
        "app.customer_intelligence.workflow.run_research", fake_run_research
    )
    monkeypatch.setattr(
        "app.customer_intelligence.jobs.SessionLocal", async_session_factory
    )

    await run_ci_research({"job_try": 1}, "org-job-ingested", case_id)

    assert called == {"org_id": "org-job-ingested", "case_id": case_id}


async def test_run_ci_research_skips_case_already_past_ingested(
    async_session_factory, monkeypatch
):
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

    monkeypatch.setattr(
        "app.customer_intelligence.workflow.run_research", fake_run_research
    )
    monkeypatch.setattr(
        "app.customer_intelligence.jobs.SessionLocal", async_session_factory
    )

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

    monkeypatch.setattr(
        "app.customer_intelligence.workflow.run_research", failing_run_research
    )
    monkeypatch.setattr(
        "app.customer_intelligence.jobs.SessionLocal", async_session_factory
    )

    await run_ci_research({"job_try": 1}, "org-job-retry", case_id)

    async with async_session_factory() as session:
        refreshed = await ResearchCaseRepository(session).get("org-job-retry", case_id)
    assert refreshed.status == "RETRYING"
    assert refreshed.retry_count == 1

    # A duplicate message while backoff is pending is a safe no-op.
    await run_ci_research({"job_try": 3}, "org-job-retry", case_id)
