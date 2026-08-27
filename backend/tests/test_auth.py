from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth.oauth import oauth
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


from app.core.quota.dependencies import _redis_client


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    async def _override_redis():
        yield None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_redis_client] = _override_redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()



def test_register_login_me(client: TestClient) -> None:
    # 1. Register
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "password": "SecretPassword123!",
            "display_name": "Alice",
            "org_name": "Alice Inc",
        },
    )
    assert reg_resp.status_code == 201
    token_data = reg_resp.json()
    assert "access_token" in token_data
    assert "refresh_token" in reg_resp.cookies

    # 2. Login
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "SecretPassword123!"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    # 3. Me
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "alice@example.com"
    assert me_data["display_name"] == "Alice"
    assert len(me_data["memberships"]) == 1
    assert me_data["memberships"][0]["org_name"] == "Alice Inc"
    assert me_data["memberships"][0]["role"] == "admin"


def test_switch_org(client: TestClient) -> None:
    # Register Alice with Org 1
    reg1 = client.post(
        "/api/auth/register",
        json={"email": "switch@example.com", "password": "Password123!", "org_name": "Org 1"},
    )
    token1 = reg1.json()["access_token"]
    me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    org1_id = me1.json()["memberships"][0]["org_id"]

    # Create Org 2
    create_org_resp = client.post(
        "/api/orgs",
        json={"name": "Org 2"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert create_org_resp.status_code == 201
    org2_id = create_org_resp.json()["id"]

    # Switch Org to Org 2
    switch_resp = client.post(
        "/api/auth/switch-org",
        json={"org_id": org2_id},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert switch_resp.status_code == 200
    token2 = switch_resp.json()["access_token"]
    assert token2 != token1

    # Verify refresh token endpoint returns token bound to Org 2 (persisted via cookie)
    refresh_resp = client.post("/api/auth/refresh")
    assert refresh_resp.status_code == 200
    refreshed_token = refresh_resp.json()["access_token"]
    
    from app.core.auth.jwt import verify_access_token
    payload = verify_access_token(refreshed_token)
    assert payload["org_id"] == org2_id

    # Switch Org to forbidden org should return 403
    forbidden_resp = client.post(
        "/api/auth/switch-org",
        json={"org_id": "non-existent-org-id"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert forbidden_resp.status_code == 403


def test_platform_admin_deletes_org_without_destroying_history(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={"email": "org-delete@example.com", "password": "Password123!", "org_name": "Delete Me"},
    )
    token = registration.json()["access_token"]
    org_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["memberships"][0]["org_id"]

    response = client.delete(f"/api/orgs/{org_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    assert client.get("/api/orgs", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_platform_admin_renames_org(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={"email": "org-rename@example.com", "password": "Password123!", "org_name": "Old Name"},
    )
    token = registration.json()["access_token"]
    org_id = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["memberships"][0]["org_id"]

    response = client.patch(
        f"/api/orgs/{org_id}",
        json={"name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"

def test_unauthenticated_request_returns_401(client: TestClient) -> None:
    client.cookies.clear()
    # Attempting to access protected endpoint without token must return 401
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_login_wrong_password_401(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": "CorrectPassword123!"},
    )
    resp = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "WrongPassword!"},
    )
    assert resp.status_code == 401


def test_refresh_rotation_rejects_old_token(client: TestClient) -> None:
    # Register & Login
    client.post(
        "/api/auth/register",
        json={"email": "carol@example.com", "password": "Password123!"},
    )
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "Password123!"},
    )
    old_refresh_cookie = login_resp.cookies.get("refresh_token")
    assert old_refresh_cookie is not None

    # 1st Refresh: succeeds & rotates token
    refresh_resp1 = client.post("/api/auth/refresh")
    assert refresh_resp1.status_code == 200
    new_refresh_cookie = refresh_resp1.cookies.get("refresh_token")
    assert new_refresh_cookie is not None
    assert new_refresh_cookie != old_refresh_cookie

    # Clear jar & send old_refresh_cookie explicitly
    client.cookies.clear()
    refresh_resp2 = client.post(
        "/api/auth/refresh", cookies={"refresh_token": old_refresh_cookie}
    )
    assert refresh_resp2.status_code == 401


def test_org_membership_isolation_403(client: TestClient) -> None:
    # Register User 1 & Org 1
    reg1 = client.post(
        "/api/auth/register",
        json={"email": "user1@example.com", "password": "Password123!", "org_name": "Org 1"},
    )
    token1 = reg1.json()["access_token"]
    me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    org1_id = me1.json()["memberships"][0]["org_id"]

    # Register User 2 & Org 2
    reg2 = client.post(
        "/api/auth/register",
        json={"email": "user2@example.com", "password": "Password123!", "org_name": "Org 2"},
    )
    token2 = reg2.json()["access_token"]

    # User 2 tries to access Org 1 members / api-keys -> MUST RETURN 403
    resp_members = client.get(
        f"/api/orgs/{org1_id}/members",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp_members.status_code == 403

    resp_keys = client.get(
        f"/api/orgs/{org1_id}/api-keys",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp_keys.status_code == 403


def test_api_key_full_value_shown_once(client: TestClient) -> None:
    # Register & Get Org ID
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "dave@example.com", "password": "Password123!"},
    )
    token = reg_resp.json()["access_token"]
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    org_id = me_resp.json()["memberships"][0]["org_id"]

    # Create API Key
    create_key_resp = client.post(
        f"/api/orgs/{org_id}/api-keys",
        json={"name": "CI Deployment Key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_key_resp.status_code == 201
    key_data = create_key_resp.json()
    assert "secret_key" in key_data
    secret_key = key_data["secret_key"]
    assert secret_key.startswith("oa_live_")

    # List API Keys: must NOT return secret_key, only prefix
    list_key_resp = client.get(
        f"/api/orgs/{org_id}/api-keys",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_key_resp.status_code == 200
    keys_list = list_key_resp.json()
    assert len(keys_list) == 1
    assert "secret_key" not in keys_list[0]
    assert keys_list[0]["key_prefix"] == secret_key[:12]

    # Test authentication with API Key header
    me_via_key = client.get("/api/auth/me", headers={"X-API-Key": secret_key})
    assert me_via_key.status_code == 200
    assert me_via_key.json()["email"] == "dave@example.com"


def test_expired_api_key_returns_401(client: TestClient) -> None:
    # Register & Create Expired API Key (-1 days)
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "eve@example.com", "password": "Password123!"},
    )
    token = reg_resp.json()["access_token"]
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    org_id = me_resp.json()["memberships"][0]["org_id"]

    create_key_resp = client.post(
        f"/api/orgs/{org_id}/api-keys",
        json={"name": "Expired Key", "expires_days": -1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_key_resp.status_code == 201
    expired_key = create_key_resp.json()["secret_key"]

    # Using expired key MUST return 401
    me_via_expired_key = client.get("/api/auth/me", headers={"X-API-Key": expired_key})
    assert me_via_expired_key.status_code == 401


def test_oauth_callback_links_existing_email(client: TestClient) -> None:
    # 1. Register normal user
    client.post(
        "/api/auth/register",
        json={"email": "oauth_user@example.com", "password": "Password123!"},
    )

    # 2. Mock OAuth google client
    mock_client = MagicMock()
    mock_client.authorize_access_token = AsyncMock(
        return_value={
            "access_token": "mock_google_token",
            "userinfo": {
                "email": "oauth_user@example.com",
                "sub": "google-sub-9999",
                "name": "OAuth User",
            },
        }
    )
    oauth.google = mock_client

    # 3. Call OAuth callback
    cb_resp = client.get("/api/auth/oauth/google/callback")
    assert cb_resp.status_code == 200
    access_token = cb_resp.json()["access_token"]

    # 4. Verify me endpoint returns linked user
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "oauth_user@example.com"


def test_jwt_access_to_existing_api_routes(client: TestClient) -> None:
    # Register User & get JWT Token
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "api_user@example.com", "password": "Password123!"},
    )
    token = reg_resp.json()["access_token"]

    # Call main API routes with Bearer JWT (verify_api_key accepts JWT and sets org_id)
    agents_resp = client.get("/api/agents", headers={"Authorization": f"Bearer {token}"})
    assert agents_resp.status_code == 200

    models_resp = client.get("/api/models", headers={"Authorization": f"Bearer {token}"})
    assert models_resp.status_code == 200


def test_tenant_override_prevention_403(client: TestClient) -> None:
    # Register User 1 & Org 1
    reg1 = client.post(
        "/api/auth/register",
        json={"email": "tenant1@example.com", "password": "Password123!", "org_name": "Org 1"},
    )
    token1 = reg1.json()["access_token"]

    # Register User 2 & Org 2
    reg2 = client.post(
        "/api/auth/register",
        json={"email": "tenant2@example.com", "password": "Password123!", "org_name": "Org 2"},
    )
    token2 = reg2.json()["access_token"]
    me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
    org2_id = me2.json()["memberships"][0]["org_id"]

    # User 1 sends Token 1 (Org 1) but attempts X-Org-Id: Org 2 -> MUST BE REJECTED 403
    override_resp = client.get(
        "/api/agents",
        headers={"Authorization": f"Bearer {token1}", "X-Org-Id": org2_id},
    )
    assert override_resp.status_code == 403


def test_update_profile_display_name_and_password(client: TestClient) -> None:
    # Register user
    reg = client.post(
        "/api/auth/register",
        json={"email": "profile_test@example.com", "password": "OldPassword123!"},
    )
    token = reg.json()["access_token"]

    # Update display name
    patch_resp = client.patch(
        "/api/auth/me",
        json={"display_name": "New Display Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["display_name"] == "New Display Name"

    # Try change password with wrong old password -> 400
    bad_pass_resp = client.patch(
        "/api/auth/me",
        json={"old_password": "WrongPassword!", "new_password": "NewPassword123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad_pass_resp.status_code == 400

    # Change password with correct old password -> 200
    good_pass_resp = client.patch(
        "/api/auth/me",
        json={"old_password": "OldPassword123!", "new_password": "NewPassword123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert good_pass_resp.status_code == 200

    # Login with new password -> 200
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "profile_test@example.com", "password": "NewPassword123!"},
    )
    assert login_resp.status_code == 200

