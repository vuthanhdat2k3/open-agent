from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app

PASSWORD = "Password@123"


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


def _auth_headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Org-Id"] = org_id
    return headers


def test_full_member_lifecycle_roles_and_removal(client: TestClient) -> None:
    # 1. Register Org Owner (Org Admin)
    owner_email = "owner_lifecycle@test.com"
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": owner_email, "password": PASSWORD, "org_name": "Lifecycle Corp"},
    )
    assert reg_resp.status_code == 201, reg_resp.text
    owner_token = reg_resp.json()["access_token"]

    me_resp = client.get("/api/auth/me", headers=_auth_headers(owner_token))
    assert me_resp.status_code == 200
    org_id = me_resp.json()["memberships"][0]["org_id"]

    # 2. Org Admin adds Operator directly (with initial password)
    operator_email = "operator_lifecycle@test.com"
    op_add_resp = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_auth_headers(owner_token, org_id),
        json={
            "email": operator_email,
            "role": "operator",
            "initial_password": PASSWORD,
        },
    )
    assert op_add_resp.status_code == 201, op_add_resp.text
    op_member_data = op_add_resp.json()
    operator_user_id = op_member_data["user_id"]
    assert op_member_data["role"] == "operator"

    # 3. Org Admin adds Workplace User directly (with initial password)
    user_email = "user_lifecycle@test.com"
    user_add_resp = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_auth_headers(owner_token, org_id),
        json={
            "email": user_email,
            "role": "user",
            "initial_password": PASSWORD,
        },
    )
    assert user_add_resp.status_code == 201, user_add_resp.text
    user_member_data = user_add_resp.json()
    user_user_id = user_member_data["user_id"]
    assert user_member_data["role"] == "user"

    # 4. Login as Operator and verify permissions
    op_login_resp = client.post(
        "/api/auth/login",
        json={"email": operator_email, "password": PASSWORD},
    )
    assert op_login_resp.status_code == 200, op_login_resp.text
    operator_token = op_login_resp.json()["access_token"]

    # Operator CAN access model/agent resources
    op_agents = client.get("/api/agents", headers=_auth_headers(operator_token, org_id))
    assert op_agents.status_code == 200

    # Operator CANNOT add members (403 Forbidden)
    op_add_forbidden = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_auth_headers(operator_token, org_id),
        json={"email": "intruder@test.com", "role": "user"},
    )
    assert op_add_forbidden.status_code == 403

    # 5. Login as Workplace User and verify permissions
    user_login_resp = client.post(
        "/api/auth/login",
        json={"email": user_email, "password": PASSWORD},
    )
    assert user_login_resp.status_code == 200, user_login_resp.text
    user_token = user_login_resp.json()["access_token"]

    # Workplace user CAN read workflows/agents
    user_agents = client.get("/api/agents", headers=_auth_headers(user_token, org_id))
    assert user_agents.status_code == 200

    # Workplace user CANNOT create agents (403 Forbidden)
    user_create_agent = client.post(
        "/api/agents",
        headers=_auth_headers(user_token, org_id),
        json={"name": "hacked-agent"},
    )
    assert user_create_agent.status_code == 403

    # Workplace user CANNOT add members (403 Forbidden)
    user_add_forbidden = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_auth_headers(user_token, org_id),
        json={"email": "intruder2@test.com", "role": "user"},
    )
    assert user_add_forbidden.status_code == 403

    # 6. Org Admin removes Workplace User
    del_resp = client.delete(
        f"/api/orgs/{org_id}/members/{user_user_id}",
        headers=_auth_headers(owner_token, org_id),
    )
    assert del_resp.status_code == 200, del_resp.text
    assert del_resp.json() == {"ok": True}

    # 7. Verify Removed User CANNOT access any protected endpoint (401/403)
    user_blocked_call = client.get(
        "/api/agents",
        headers=_auth_headers(user_token, org_id),
    )
    assert user_blocked_call.status_code in {401, 403}

    # 8. Verify Removed User CANNOT log in (403 User belongs to no organization)
    user_relogin = client.post(
        "/api/auth/login",
        json={"email": user_email, "password": PASSWORD},
    )
    assert user_relogin.status_code in {401, 403, 404}

    # 9. Org Admin re-adds Workplace User -> Verify account is re-activated cleanly
    readd_resp = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_auth_headers(owner_token, org_id),
        json={
            "email": user_email,
            "role": "user",
            "initial_password": "NewPassword@123",
        },
    )
    assert readd_resp.status_code == 201, readd_resp.text

    # Verify user can log in with new password
    reactivated_login = client.post(
        "/api/auth/login",
        json={"email": user_email, "password": "NewPassword@123"},
    )
    assert reactivated_login.status_code == 200, reactivated_login.text

    # 10. Owner cannot remove themselves (400 Bad Request)
    owner_user_id = me_resp.json()["id"]
    self_del = client.delete(
        f"/api/orgs/{org_id}/members/{owner_user_id}",
        headers=_auth_headers(owner_token, org_id),
    )
    assert self_del.status_code == 400
    assert "You cannot remove your own membership" in self_del.text
