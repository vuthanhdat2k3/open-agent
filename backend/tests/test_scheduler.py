from datetime import datetime, timedelta

import pytest
from prometheus_client import generate_latest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.observability.metrics import (
    ci_cases_ingested_total,
    ci_syncs_total,
)
from app.customer_intelligence.ingest import sync_connection
from app.customer_intelligence.scheduler import compute_next_run_at, run_due_schedules
from app.customer_intelligence.security import encrypt_credentials
from app.db.base import Base, utc_now
from app.models.customer_intelligence import (
    CiSchedule,
    EmailConnection,
    InboundEmail,
    ResearchCase,
)
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
def ci_mcp_fixture(ci_mcp_stub):
    return ci_mcp_stub


def _seed_scheduled_mailbox(org_id: str) -> None:
    return None


async def _seed_scheduled_connection(
    async_session_factory, org_id: str, *, schedule_due: bool, run_time: str = "06:00"
) -> tuple[str, str]:
    now = utc_now()
    async with async_session_factory() as session:
        conn = EmailConnection(
            org_id=org_id,
            provider="gmail",
            account_email="fake@example.com",
            status="connected",
            credentials_enc=encrypt_credentials({"access_token": "test"}),
            created_by_user_id="test-user",
        )
        session.add(conn)
        await session.flush()
        workflow = Workflow(org_id=org_id, created_by_user_id="test-user", name="Gmail monitor", graph={"nodes": [], "edges": []})
        session.add(workflow)
        await session.flush()
        session.add(WorkflowInstallation(org_id=org_id, owner_user_id="test-user", template_key="gmail_monitor_and_triage", template_version=1, workflow_id=workflow.id, name="Gmail monitor", status="enabled", settings={"connection_id": conn.id}))
        schedule = CiSchedule(
            org_id=org_id,
            connection_id=conn.id,
            enabled=True,
            run_time=run_time,
            timezone="UTC",
            next_run_at=now - timedelta(hours=1) if schedule_due else now + timedelta(hours=1),
        )
        session.add(schedule)
        await session.commit()
        return conn.id, schedule.id


def _seed_mailbox(org_id: str) -> None:
    return None


def _counter_value(counter, **labels: str) -> float:
    return counter.labels(**labels).collect()[0].samples[0].value


# --- compute_next_run_at ----------------------------------------------------


def test_next_run_utc_future_same_day():
    now = datetime(2026, 3, 10, 5, 30)
    assert compute_next_run_at("06:00", "UTC", now) == datetime(2026, 3, 10, 6, 0)


def test_next_run_utc_passed_rolls_to_tomorrow():
    now = datetime(2026, 3, 10, 7, 0)
    assert compute_next_run_at("06:00", "UTC", now) == datetime(2026, 3, 11, 6, 0)


def test_compute_next_run_bangkok_offset():
    # Bangkok is UTC+7: 2026-03-10 23:00 UTC == 2026-03-11 06:00 BKK, which has
    # just occurred, so the next 06:00 BKK is 2026-03-12 06:00 BKK == 23:00 UTC.
    now = datetime(2026, 3, 10, 23, 0)
    assert compute_next_run_at("06:00", "Asia/Bangkok", now) == datetime(2026, 3, 11, 23, 0)


def test_compute_next_run_midnight_wrap():
    now = datetime(2026, 3, 10, 0, 0)
    assert compute_next_run_at("00:00", "UTC", now) == datetime(2026, 3, 11, 0, 0)


def test_compute_next_run_unknown_zone_falls_back_to_utc():
    now = datetime(2026, 3, 10, 15, 0)
    assert compute_next_run_at("16:00", "Not/AZone", now) == datetime(2026, 3, 10, 16, 0)


def test_compute_next_run_rejects_invalid_time():
    with pytest.raises(ValueError, match="run_time must be HH:MM"):
        compute_next_run_at("25:00", "UTC", datetime(2026, 3, 10, 5, 30))


async def test_run_due_synchronizes_and_advances(async_session_factory, ci_mcp_stub):
    now = utc_now()
    conn_id, schedule_id = await _seed_scheduled_connection(
        async_session_factory, "org-due-0001", schedule_due=True
    )
    _seed_mailbox("org-due-0001")

    async with async_session_factory() as session:
        summary = await run_due_schedules(session, now=now)
        assert summary["due"] == 1
        assert summary["processed"] == [schedule_id]
        assert summary["failed"] == []

        emails = (await session.execute(select(InboundEmail).where(InboundEmail.connection_id == conn_id))).scalars().all()
        cases = (await session.execute(select(ResearchCase).where(ResearchCase.connection_id == conn_id))).scalars().all()
        assert len(emails) == 1
        assert len(cases) == 0
        assert emails[0].classification == "queued"

        schedule = (await session.execute(select(CiSchedule))).scalar_one()
        assert schedule.last_run_at == now
        assert schedule.next_run_at > now


async def test_run_due_skips_future_schedule(async_session_factory, ci_mcp_stub):
    await _seed_scheduled_connection(async_session_factory, "org-fut-0002", schedule_due=False)

    async with async_session_factory() as session:
        summary = await run_due_schedules(session, now=utc_now())
        assert summary["due"] == 0
        assert summary["processed"] == []
        assert summary["failed"] == []


async def test_manual_sync_observes_metrics(async_session_factory, ci_mcp_stub):
    now = utc_now()
    conn_id, _ = await _seed_scheduled_connection(
        async_session_factory, "org-met-0004", schedule_due=True
    )
    _seed_mailbox("org-met-0004")

    before_success = _counter_value(ci_syncs_total, result="success")
    before_cases = _counter_value(ci_cases_ingested_total, trigger="manual")

    async with async_session_factory() as session:
        result = await sync_connection(
            session, org_id="org-met-0004", connection_id=conn_id, trigger="manual"
        )
        assert result["synced"] == 1
        assert result["new_cases"] == 0
        assert result["classification_queued"] == 1

    assert _counter_value(ci_syncs_total, result="success") == before_success + 1
    assert _counter_value(ci_cases_ingested_total, trigger="manual") == before_cases


async def test_scheduled_sync_observes_scheduled_trigger_metric(
    async_session_factory, ci_mcp_stub
):
    now = utc_now()
    await _seed_scheduled_connection(async_session_factory, "org-sch-0005", schedule_due=True)
    _seed_mailbox("org-sch-0005")

    before = _counter_value(ci_cases_ingested_total, trigger="scheduled")

    async with async_session_factory() as session:
        summary = await run_due_schedules(session, now=now)
        assert summary["processed"]

    assert _counter_value(ci_cases_ingested_total, trigger="scheduled") == before


async def test_ci_metrics_expose_no_identifiers(async_session_factory, ci_mcp_stub):
    # M6 requirement: metrics labels must not leak PII. org/connection/schedule
    # ids are deliberately absent from every emitted ci_* series.
    org_id = "org-pii-0009"
    conn_id, schedule_id = await _seed_scheduled_connection(
        async_session_factory, org_id, schedule_due=True
    )
    _seed_mailbox(org_id)
    async with async_session_factory() as session:
        await sync_connection(session, org_id=org_id, connection_id=conn_id, trigger="manual")

    latest = generate_latest().decode()
    ci_block = "\n".join(
        line for line in latest.splitlines()
        if line.startswith("# HELP ci_") or line.startswith("# TYPE ci_") or line.startswith("ci_")
    )
    assert org_id not in ci_block
    assert conn_id not in ci_block
    assert schedule_id not in ci_block
