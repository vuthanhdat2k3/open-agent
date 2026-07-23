from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    assert me_data["memberships"][0]["role"] == "owner"


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
    refresh_resp2 = client.post("/api/auth/refresh", cookies={"refresh_token": old_refresh_cookie})
    assert refresh_resp2.status_code == 401


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
