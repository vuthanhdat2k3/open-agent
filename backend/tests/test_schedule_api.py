from __future__ import annotations

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.customer_intelligence.security import encrypt_credentials
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.customer_intelligence import EmailConnection


@pytest.fixture
async def async_session_factory():
    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def ci_enabled(monkeypatch):
    monkeypatch.setenv("OPENAGENT_CUSTOMER_INTELLIGENCE_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _register(client: TestClient, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Secret123!", "org_name": "ScheduleOrg"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["memberships"][0]["org_id"]


def _seed_connection(async_session_factory, org_id: str) -> str:
    async def _seed() -> str:
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

    return anyio.run(_seed)


def _seed_mailbox(org_id: str) -> None:
    return None


def test_schedule_crud_flow(client: TestClient, async_session_factory, ci_enabled) -> None:
    token, org_id = _register(client, "sched-owner-1@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    conn_id = _seed_connection(async_session_factory, org_id)

    created = client.post(
        "/api/customer-intelligence/schedules",
        headers=header,
        json={"connection_id": conn_id, "run_time": "06:00", "timezone": "UTC"},
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]
    assert created.json()["enabled"] is True
    assert created.json()["next_run_at"] is not None

    listed = client.get("/api/customer-intelligence/schedules", headers=header)
    assert listed.status_code == 200, listed.text
    assert [s["id"] for s in listed.json()] == [schedule_id]

    updated = client.patch(
        f"/api/customer-intelligence/schedules/{schedule_id}",
        headers=header,
        json={"enabled": False, "run_time": "09:30"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is False
    assert updated.json()["run_time"] == "09:30"

    deleted = client.delete(f"/api/customer-intelligence/schedules/{schedule_id}", headers=header)
    assert deleted.status_code == 204, deleted.text

    after = client.get("/api/customer-intelligence/schedules", headers=header)
    assert after.json() == []


def test_create_schedule_unknown_connection_404(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    token, org_id = _register(client, "sched-owner-2@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    resp = client.post(
        "/api/customer-intelligence/schedules",
        headers=header,
        json={"connection_id": "no-such-conn", "run_time": "06:00"},
    )
    assert resp.status_code == 404, resp.text


def test_schedule_manual_run_syncs_and_advances(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    token, org_id = _register(client, "sched-owner-3@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    conn_id = _seed_connection(async_session_factory, org_id)
    _seed_mailbox(org_id)

    created = client.post(
        "/api/customer-intelligence/schedules",
        headers=header,
        json={"connection_id": conn_id, "run_time": "06:00"},
    )
    schedule_id = created.json()["id"]

    run = client.post(f"/api/customer-intelligence/schedules/{schedule_id}/run", headers=header)
    assert run.status_code == 200, run.text
    assert run.json()["synced"] == 1
    assert run.json()["new_cases"] == 1

    listed = client.get("/api/customer-intelligence/schedules", headers=header)
    schedule = next(s for s in listed.json() if s["id"] == schedule_id)
    assert schedule["last_run_at"] is not None
    assert schedule["next_run_at"] is not None


def test_schedule_manual_run_unknown_schedule_404(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    token, org_id = _register(client, "sched-owner-4@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    resp = client.post(
        "/api/customer-intelligence/schedules/no-such-id/run", headers=header
    )
    assert resp.status_code == 404, resp.text


def test_schedule_disabled_manual_run_400(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    token, org_id = _register(client, "sched-owner-5@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    conn_id = _seed_connection(async_session_factory, org_id)

    created = client.post(
        "/api/customer-intelligence/schedules",
        headers=header,
        json={"connection_id": conn_id, "run_time": "06:00", "enabled": False},
    )
    schedule_id = created.json()["id"]

    resp = client.post(f"/api/customer-intelligence/schedules/{schedule_id}/run", headers=header)
    assert resp.status_code == 400, resp.text


def test_schedule_ops_write_audit_rows_with_correlation_id(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    token, org_id = _register(client, "sched-owner-6@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    conn_id = _seed_connection(async_session_factory, org_id)
    _seed_mailbox(org_id)

    created = client.post(
        "/api/customer-intelligence/schedules",
        headers=header,
        json={"connection_id": conn_id, "run_time": "06:00"},
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    run = client.post(f"/api/customer-intelligence/schedules/{schedule_id}/run", headers=header)
    assert run.status_code == 200, run.text
    correlation_id = run.json().get("correlation_id")
    assert correlation_id, "run response must carry a correlation id"

    async def _rows(action: str) -> list[AuditLog]:
        async with async_session_factory() as session:
            res = await session.execute(
                select(AuditLog).where(
                    AuditLog.org_id == org_id,
                    AuditLog.action == action,
                )
            )
            return list(res.scalars().all())

    created_rows = anyio.run(_rows, "ci.schedule.created")
    assert len(created_rows) == 1
    assert created_rows[0].resource_id == schedule_id

    ran_rows = anyio.run(_rows, "ci.schedule.ran")
    assert len(ran_rows) == 1
    assert ran_rows[0].metadata_["correlation_id"] == correlation_id
    assert ran_rows[0].metadata_["synced"] == 1

    synced_rows = anyio.run(_rows, "ci.connection.synced")
    assert len(synced_rows) == 1
    assert synced_rows[0].metadata_["correlation_id"] == correlation_id

    updated = client.patch(
        f"/api/customer-intelligence/schedules/{schedule_id}",
        headers=header,
        json={"enabled": False},
    )
    assert updated.status_code == 200, updated.text
    updated_rows = anyio.run(_rows, "ci.schedule.updated")
    assert len(updated_rows) == 1
    assert updated_rows[0].metadata_["enabled"] is False

    deleted = client.delete(f"/api/customer-intelligence/schedules/{schedule_id}", headers=header)
    assert deleted.status_code == 204, deleted.text
    deleted_rows = anyio.run(_rows, "ci.schedule.deleted")
    assert len(deleted_rows) == 1
    assert deleted_rows[0].resource_id == schedule_id
