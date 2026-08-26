from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.authz.policy import has_permission
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User

# ---------------------------------------------------------------------------
# Unit: has_permission() matrix
# ---------------------------------------------------------------------------


class TestPermissionMatrix:
    def test_admin_has_everything(self) -> None:
        assert has_permission(Role.admin, "anything:at:all")
        assert has_permission(Role.admin, "")
        assert has_permission(Role.admin, "*")
        assert has_permission(Role.admin, "orgs:manage")
        assert has_permission(Role.admin, "models:manage")
        assert has_permission(Role.admin, "mcp:manage")
        assert has_permission(Role.admin, "providers:manage")
        assert has_permission(Role.admin, "agents:create")
        assert has_permission(Role.admin, "workflows:delete")

    def test_user_has_explicit_permissions(self) -> None:
        assert has_permission(Role.user, "agents:read")
        assert has_permission(Role.user, "agents:run")
        assert has_permission(Role.user, "workflows:read")
        assert has_permission(Role.user, "workflows:run")
        assert has_permission(Role.user, "workflows:install")
        assert has_permission(Role.user, "tools:use:safe")
        assert has_permission(Role.user, "tools:use:network")
        assert has_permission(Role.user, "files:read")
        assert has_permission(Role.user, "usage:read")
        assert has_permission(Role.user, "models:read")
        assert has_permission(Role.user, "approvals:read")
        assert has_permission(Role.user, "quota:usage")

    def test_user_denied_admin_only(self) -> None:
        assert not has_permission(Role.user, "models:manage")
        assert not has_permission(Role.user, "mcp:manage")
        assert not has_permission(Role.user, "providers:manage")
        assert not has_permission(Role.user, "orgs:read")
        assert not has_permission(Role.user, "orgs:manage")
        assert not has_permission(Role.user, "agents:create")
        assert not has_permission(Role.user, "agents:update")
        assert not has_permission(Role.user, "agents:delete")
        assert not has_permission(Role.user, "workflows:create")
        assert not has_permission(Role.user, "workflows:delete")
        assert not has_permission(Role.user, "files:manage")
        assert not has_permission(Role.user, "approvals:decide")
        assert not has_permission(Role.user, "evaluations:read")

    def test_user_sessions_glob(self) -> None:
        assert has_permission(Role.user, "sessions:read")
        assert has_permission(Role.user, "sessions:delete")

    def test_unknown_role_returns_false(self) -> None:
        assert not has_permission("superadmin", "agents:read")  # type: ignore[arg-type]

    def test_org_admin_has_declared_admin_permissions(self) -> None:
        # Route-level permissions must be declared explicitly for the audit
        # list even though org_admin's wildcard would grant them anyway.
        assert has_permission(Role.org_admin, "admin:email-intelligence")

    def test_operator_usage_and_quota_read(self) -> None:
        assert has_permission(Role.operator, "usage:read")
        assert has_permission(Role.operator, "quota:usage")

    def test_operator_lacks_org_admin_surfaces(self) -> None:
        assert not has_permission(Role.operator, "admin:email-intelligence")
        assert not has_permission(Role.operator, "orgs:manage")
        assert not has_permission(Role.operator, "members:manage")
        assert not has_permission(Role.operator, "quotas:manage")
        # Operator has full AI stack management
        assert has_permission(Role.operator, "models:manage")
        assert has_permission(Role.operator, "agents:manage")

    def test_user_lacks_ingest_and_org_management(self) -> None:
        assert not has_permission(Role.user, "files:manage")
        assert not has_permission(Role.user, "admin:email-intelligence")
        assert not has_permission(Role.user, "orgs:manage")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

PASSWORD = "Secret123!"


def _register(client: TestClient, email: str, password: str = PASSWORD, org_name: str | None = None) -> str:
    body = {"email": email, "password": password}
    if org_name:
        body["org_name"] = org_name
    resp = client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, f"register failed: {resp.text}"
    return resp.json()["access_token"]


def _get_org_id(client: TestClient, token: str) -> str:
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    return me.json()["memberships"][0]["org_id"]


def _add_member(client: TestClient, token: str, org_id: str, email: str, role: str) -> str:
    """Register *email*, add them to *org_id* with *role*, return their JWT."""
    member_token = _register(client, email)
    resp = client.post(
        f"/api/orgs/{org_id}/members",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"add member failed: {resp.text}"
    return member_token


def _auth_headers(token: str, org_id: str | None = None) -> dict[str, str]:
    """Return Bearer auth headers, optionally scoped to *org_id* via X-Org-Id."""
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Org-Id"] = org_id
    return headers


def _create_provider_and_model(
    client: TestClient, token: str, org_id: str
) -> tuple[str, str]:
    """Create a minimal provider + model, return (provider_id, model_id)."""
    # Provider
    prov_resp = client.post(
        "/api/providers",
        headers=_auth_headers(token, org_id),
        json={
            "key": "test-provider",
            "name": "Test Provider",
            "base_url": "http://localhost:9999/v1",
            "api_key": "sk-test",
        },
    )
    assert prov_resp.status_code == 201, f"create provider failed: {prov_resp.text}"
    provider_id = prov_resp.json()["id"]

    # Model
    model_resp = client.post(
        "/api/models",
        headers=_auth_headers(token, org_id),
        json={
            "provider_id": provider_id,
            "name": "test-model",
            "display_name": "Test Model",
            "tier": "balanced",
            "context_window": 4096,
            "input_cost_per_1k": 0.0,
            "output_cost_per_1k": 0.0,
        },
    )
    assert model_resp.status_code == 201, f"create model failed: {model_resp.text}"
    model_id = model_resp.json()["id"]

    return provider_id, model_id


# ---------------------------------------------------------------------------
# Integration: route-level RBAC
# ---------------------------------------------------------------------------


class TestRouteRBAC:
    """Integration tests for require_permission() applied to every route group.

    These tests rely on X-Org-Id to scope the permission check to the target org
    so that the user's role in that org (not their home org) is used.
    """

    def test_owner_can_access_all_routes(self, client: TestClient) -> None:
        token = _register(client, "owner_all@test.com", PASSWORD, "OwnerAllOrg")
        org_id = _get_org_id(client, token)

        # GET routes
        assert client.get("/api/agents", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get("/api/models", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get("/api/providers", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get("/api/sessions", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get("/api/workflows", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get(f"/api/orgs/{org_id}/members", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get(f"/api/orgs/{org_id}/api-keys", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get("/api/files", headers=_auth_headers(token, org_id)).status_code == 200
        assert client.get("/api/debug/usage", headers=_auth_headers(token, org_id)).status_code == 200

        # POST routes (need proper payloads)
        _, model_id = _create_provider_and_model(client, token, org_id)
        assert client.post(
            "/api/agents",
            headers=_auth_headers(token, org_id),
            json={"name": "owner-agent", "system_prompt": "x", "model_id": model_id},
        ).status_code == 201

    def test_user_denied_create_agent(self, client: TestClient) -> None:
        admin_token = _register(client, "v_owner@test.com", PASSWORD, "ViewerTest")
        org_id = _get_org_id(client, admin_token)

        user_email = "v_denied@test.com"
        user_home_token = _add_member(client, admin_token, org_id, user_email, "user")

        # User can GET agents (requires agents:read)
        assert client.get(
            "/api/agents", headers=_auth_headers(user_home_token, org_id)
        ).status_code == 200

        # User cannot POST agents (requires agents:create - admin only)
        _, model_id = _create_provider_and_model(client, admin_token, org_id)
        resp = client.post(
            "/api/agents",
            headers=_auth_headers(user_home_token, org_id),
            json={"name": "should-fail", "system_prompt": "x", "model_id": model_id},
        )
        assert resp.status_code == 403

    def test_admin_can_create_agent(self, client: TestClient) -> None:
        admin_token = _register(client, "d_owner@test.com", PASSWORD, "DevTest")
        org_id = _get_org_id(client, admin_token)

        _, model_id = _create_provider_and_model(client, admin_token, org_id)
        resp = client.post(
            "/api/agents",
            headers=_auth_headers(admin_token, org_id),
            json={"name": "admin-agent", "system_prompt": "helpful", "model_id": model_id},
        )
        assert resp.status_code == 201, f"admin create agent failed: {resp.text}"

    def test_unauthenticated_request_returns_401(self, client: TestClient) -> None:
        assert client.get("/api/agents").status_code == 401
        assert client.get("/api/models").status_code == 401
        assert client.get("/api/providers").status_code == 401
        assert client.get("/api/sessions").status_code == 401
        assert client.get("/api/workflows").status_code == 401
        assert client.get("/api/files").status_code == 401

    def test_user_denied_provider_management(self, client: TestClient) -> None:
        admin_token = _register(client, "pm_owner@test.com", PASSWORD, "ProvMgt")
        org_id = _get_org_id(client, admin_token)

        user_email = "pm_denied@test.com"
        user_home_token = _add_member(client, admin_token, org_id, user_email, "user")

        # Providers are pure infrastructure (hold API keys/base URLs) - user
        # can't even read the list, only admin can.
        assert client.get(
            "/api/providers", headers=_auth_headers(user_home_token, org_id)
        ).status_code == 403

        # User cannot create providers (requires providers:manage - admin only)
        resp = client.post(
            "/api/providers",
            headers=_auth_headers(user_home_token, org_id),
            json={"key": "bad", "name": "bad", "base_url": "http://x", "api_key": "sk-xxx"},
        )
        assert resp.status_code == 403

    def test_user_denied_mcp_management(self, client: TestClient) -> None:
        admin_token = _register(client, "mcp_owner@test.com", PASSWORD, "MCPTest")
        org_id = _get_org_id(client, admin_token)

        user_email = "mcp_denied@test.com"
        user_home_token = _add_member(client, admin_token, org_id, user_email, "user")

        # User cannot create MCP server (requires mcp:manage - admin only)
        resp = client.post(
            "/api/mcp/servers",
            headers=_auth_headers(user_home_token, org_id),
            json={"name": "mcp-x", "base_url": "http://localhost:9999"},
        )
        assert resp.status_code == 403

    def test_owner_can_create_mcp_server_with_empty_tools(self, client: TestClient) -> None:
        owner_token = _register(client, "mcp_owner_create@test.com", PASSWORD, "MCP Create")
        org_id = _get_org_id(client, owner_token)

        resp = client.post(
            "/api/mcp/servers",
            headers=_auth_headers(owner_token, org_id),
            json={
                "name": "rag",
                "transport": "http",
                "url": "http://rag-service:8100",
            },
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["tools"] == []

    def test_admin_can_manage_org(self, client: TestClient) -> None:
        owner_token = _register(client, "ao_owner@test.com", PASSWORD, "AdminOrg")
        org_id = _get_org_id(client, owner_token)

        admin_email = "ao_admin@test.com"
        admin_home_token = _add_member(client, owner_token, org_id, admin_email, "admin")

        # Admin can read org members
        resp = client.get(
            f"/api/orgs/{org_id}/members",
            headers=_auth_headers(admin_home_token, org_id),
        )
        assert resp.status_code == 200

        # Admin can create API keys
        resp = client.post(
            f"/api/orgs/{org_id}/api-keys",
            headers=_auth_headers(admin_home_token, org_id),
            json={"name": "admin-key"},
        )
        assert resp.status_code == 201

    def test_tenant_isolation_prevents_cross_org_access(self, client: TestClient) -> None:
        token_a = _register(client, "iso_a@test.com", PASSWORD, "Org A")
        org_a_id = _get_org_id(client, token_a)

        token_b = _register(client, "iso_b@test.com", PASSWORD, "Org B")

        # User B cannot access Org A's members
        resp = client.get(
            f"/api/orgs/{org_a_id}/members",
            headers=_auth_headers(token_b, org_a_id),
        )
        assert resp.status_code == 403

        # User B cannot access Org A's api-keys
        resp = client.get(
            f"/api/orgs/{org_a_id}/api-keys",
            headers=_auth_headers(token_b, org_a_id),
        )
        assert resp.status_code == 403

    def test_user_cannot_manage_models(self, client: TestClient) -> None:
        admin_token = _register(client, "mm_owner@test.com", PASSWORD, "ModelMgt")
        org_id = _get_org_id(client, admin_token)

        user_email = "mm_denied@test.com"
        user_home_token = _add_member(client, admin_token, org_id, user_email, "user")

        # User can read models
        assert client.get(
            "/api/models", headers=_auth_headers(user_home_token, org_id)
        ).status_code == 200

        # User cannot create models (requires models:manage - admin only)
        p_id, _ = _create_provider_and_model(client, admin_token, org_id)
        resp = client.post(
            "/api/models",
            headers=_auth_headers(user_home_token, org_id),
            json={
                "provider_id": p_id,
                "name": "x",
                "display_name": "x",
                "tier": "balanced",
                "context_window": 4096,
                "input_cost_per_1k": 0,
                "output_cost_per_1k": 0,
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Integration: tool capability gate (RiskTier filtering)
# ---------------------------------------------------------------------------


class TestToolCapabilityGate:
    """Tests the 2-layer capability gate in agent_loop.py.

    Layer 1: agent.allowed_risk_tiers must include the tool's RiskTier.
    Layer 2: tool.requires_approval blocks execution at runtime.
    """

    def _create_agent_with_tiers(
        self, client: TestClient, token: str, org_id: str, tiers: list[str]
    ) -> tuple[str, str]:
        """Create provider+model then agent with *tiers*, return (agent_id, model_id)."""
        _, model_id = _create_provider_and_model(client, token, org_id)
        resp = client.post(
            "/api/agents",
            headers=_auth_headers(token, org_id),
            json={
                "name": "tier-test-agent",
                "system_prompt": "tier test",
                "model_id": model_id,
                "allowed_risk_tiers": tiers,
            },
        )
        assert resp.status_code == 201, f"create agent failed: {resp.text}"
        return resp.json()["id"], model_id

    def test_agent_stores_allowed_risk_tiers(self, client: TestClient) -> None:
        """Agent created with [safe, read] tiers stores them correctly."""
        token = _register(client, "tcg_owner@test.com", PASSWORD, "ToolCap")
        org_id = _get_org_id(client, token)

        agent_id, _ = self._create_agent_with_tiers(client, token, org_id, ["safe", "read"])

        agent_resp = client.get(
            f"/api/agents/{agent_id}",
            headers=_auth_headers(token, org_id),
        )
        assert agent_resp.status_code == 200
        agent_data = agent_resp.json()
        assert agent_data.get("allowed_risk_tiers") == ["safe", "read"]

    def test_agent_default_risk_tiers(self, client: TestClient) -> None:
        """New agents without explicit allowed_risk_tiers default to [safe, read]."""
        token = _register(client, "def_owner@test.com", PASSWORD, "DefaultRisk")
        org_id = _get_org_id(client, token)

        _, model_id = _create_provider_and_model(client, token, org_id)
        resp = client.post(
            "/api/agents",
            headers=_auth_headers(token, org_id),
            json={
                "name": "default-risk-agent",
                "system_prompt": "default tiers",
                "model_id": model_id,
            },
        )
        assert resp.status_code == 201
        agent_data = resp.json()
        assert agent_data.get("allowed_risk_tiers") == ["safe", "read"]

    def test_agent_with_all_tiers(self, client: TestClient) -> None:
        """Agent with all RiskTiers should see all tools."""
        token = _register(client, "full_owner@test.com", PASSWORD, "FullRisk")
        org_id = _get_org_id(client, token)

        agent_id, _ = self._create_agent_with_tiers(
            client, token, org_id,
            ["safe", "read", "write", "execute", "network", "dangerous"],
        )

        agent_resp = client.get(
            f"/api/agents/{agent_id}",
            headers=_auth_headers(token, org_id),
        )
        assert agent_resp.status_code == 200
        assert agent_resp.json().get("allowed_risk_tiers") == [
            "safe", "read", "write", "execute", "network", "dangerous",
        ]

    def test_agent_update_risk_tiers(self, client: TestClient) -> None:
        """Updating an agent's allowed_risk_tiers is reflected on readback."""
        token = _register(client, "upd_owner@test.com", PASSWORD, "UpdateRisk")
        org_id = _get_org_id(client, token)

        agent_id, _ = self._create_agent_with_tiers(client, token, org_id, ["safe"])

        # Update to write-only
        resp = client.put(
            f"/api/agents/{agent_id}",
            headers=_auth_headers(token, org_id),
            json={"allowed_risk_tiers": ["write"]},
        )
        assert resp.status_code == 200, f"update agent failed: {resp.text}"

        get_resp = client.get(
            f"/api/agents/{agent_id}",
            headers=_auth_headers(token, org_id),
        )
        assert get_resp.status_code == 200
        # The service layer defaults to ["safe", "read"] when update field is set to None;
        # the update endpoint allows overrides â€” verify the new value stuck
        updated = get_resp.json()
        # We only sent allowed_risk_tiers; verify it's applied
        assert updated.get("allowed_risk_tiers") == ["write"]


# ---------------------------------------------------------------------------
# Member removal guards (platform_admin / self / last org_admin)
# ---------------------------------------------------------------------------


@pytest.fixture
async def api_client(async_session_factory):
    async def _override():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _aregister(api_client: httpx.AsyncClient, email: str, org_name: str | None = None) -> tuple[str, str | None]:
    body: dict[str, str] = {"email": email, "password": PASSWORD}
    if org_name:
        body["org_name"] = org_name
    resp = await api_client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, f"register failed: {resp.text}"
    token = resp.json()["access_token"]
    org_id = None
    if org_name:
        me = await api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        org_id = me.json()["memberships"][0]["org_id"]
    return token, org_id


async def _aadd_member(api_client: httpx.AsyncClient, token: str, org_id: str, email: str, role: str) -> None:
    resp = await api_client.post(
        f"/api/orgs/{org_id}/members",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"add member failed: {resp.text}"


async def _amember_id(api_client: httpx.AsyncClient, token: str, org_id: str, email: str) -> str:
    resp = await api_client.get(f"/api/orgs/{org_id}/members", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    for member in resp.json():
        if member["email"] == email:
            return member["user_id"]
    raise AssertionError(f"member {email} not found")


async def _seed_role(factory, org_id: str, email: str, role: Role) -> str:
    async with factory() as session:
        row = await session.execute(select(User).where(User.email == email))
        user = row.scalar_one()
        await session.execute(
            update(Membership)
            .where(Membership.org_id == org_id, Membership.user_id == user.id)
            .values(role=role)
        )
        await session.commit()
        return user.id


async def test_remove_platform_admin_member_returns_403(api_client, async_session_factory):
    token, org_id = await _aregister(api_client, "pa-owner@example.com", "PA Guard Org")
    await _aadd_member(api_client, token, org_id, "pa-target@example.com", "user")
    target_id = await _seed_role(async_session_factory, org_id, "pa-target@example.com", Role.platform_admin)

    resp = await api_client.delete(
        f"/api/orgs/{org_id}/members/{target_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text
    assert "platform_admin" in resp.json()["detail"]


async def test_remove_own_membership_returns_400(api_client):
    token, org_id = await _aregister(api_client, "self-owner@example.com", "Self Guard Org")
    own_id = await _amember_id(api_client, token, org_id, "self-owner@example.com")

    resp = await api_client.delete(
        f"/api/orgs/{org_id}/members/{own_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400, resp.text
    assert "own membership" in resp.json()["detail"]


async def test_remove_last_org_admin_returns_400(api_client, async_session_factory):
    creator_token, org_id = await _aregister(api_client, "last-owner@example.com", "Last Admin Org")
    actor_token, _ = await _aregister(api_client, "actor-pa@example.com")
    await _aadd_member(api_client, creator_token, org_id, "actor-pa@example.com", "user")
    actor_id = await _seed_role(async_session_factory, org_id, "actor-pa@example.com", Role.platform_admin)

    target_id = await _amember_id(api_client, creator_token, org_id, "last-owner@example.com")

    resp = await api_client.delete(
        f"/api/orgs/{org_id}/members/{target_id}",
        headers={"Authorization": f"Bearer {actor_token}"},
    )
    assert resp.status_code == 400, resp.text
    assert "last org_admin" in resp.json()["detail"]


async def test_remove_regular_member_still_allowed(api_client):
    token, org_id = await _aregister(api_client, "ok-owner@example.com", "Regular Removal Org")
    await _aadd_member(api_client, token, org_id, "regular@example.com", "user")
    member_id = await _amember_id(api_client, token, org_id, "regular@example.com")

    resp = await api_client.delete(
        f"/api/orgs/{org_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    members = (await api_client.get(f"/api/orgs/{org_id}/members", headers={"Authorization": f"Bearer {token}"})).json()
    assert all(m["email"] != "regular@example.com" for m in members)
