from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.guardrails.approval import request_approval
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _register(client: TestClient, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Secret123!", "org_name": "ApprovalOrg"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["memberships"][0]["org_id"]


def test_approval_request_helper_and_decision_route(client: TestClient, async_session_factory) -> None:
    token, org_id = _register(client, "approval-owner@test.com")

    async def _seed() -> str:
        async with async_session_factory() as session:
            approval = await request_approval(
                session,
                org_id=org_id,
                run_type="agent",
                run_id="run-1",
                tool_name="run_shell",
                args_snapshot={"command": "whoami"},
                requested_by=None,
            )
            return approval.id

    import anyio

    approval_id = anyio.run(_seed)
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    pending = client.get("/api/approvals", headers=headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()[0]["id"] == approval_id

    decided = client.post(
        f"/api/approvals/{approval_id}/decide",
        headers=headers,
        json={"decision": "approved", "reason": "looks expected"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    assert decided.json()["reason"] == "looks expected"

    no_pending = client.get("/api/approvals", headers=headers)
    assert no_pending.status_code == 200
    assert no_pending.json() == []

