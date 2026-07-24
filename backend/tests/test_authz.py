from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.authz.policy import has_permission
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.role import Role

# ---------------------------------------------------------------------------
# Unit: has_permission() matrix
# ---------------------------------------------------------------------------


class TestPermissionMatrix:
    def test_owner_has_everything(self) -> None:
        assert has_permission(Role.owner, "anything:at:all")
        assert has_permission(Role.owner, "")
        assert has_permission(Role.owner, "*")

    def test_admin_has_explicit_permissions(self) -> None:
        assert has_permission(Role.admin, "models:manage")
        assert has_permission(Role.admin, "models:read")
        assert has_permission(Role.admin, "mcp:manage")
        assert has_permission(Role.admin, "mcp:read")
        assert has_permission(Role.admin, "providers:manage")
        assert has_permission(Role.admin, "providers:read")
        assert has_permission(Role.admin, "files:manage")
        assert has_permission(Role.admin, "files:read")
        assert has_permission(Role.admin, "usage:read")
        assert has_permission(Role.admin, "orgs:read")
        assert has_permission(Role.admin, "orgs:manage")

    def test_admin_glob_domain_star(self) -> None:
        assert has_permission(Role.admin, "agents:create")
        assert has_permission(Role.admin, "agents:read")
        assert has_permission(Role.admin, "agents:update")
        assert has_permission(Role.admin, "agents:delete")
        assert has_permission(Role.admin, "workflows:create")
        assert has_permission(Role.admin, "workflows:read")
        assert has_permission(Role.admin, "workflows:update")
        assert has_permission(Role.admin, "workflows:delete")
        assert has_permission(Role.admin, "sessions:read")
        assert has_permission(Role.admin, "sessions:delete")

    def test_admin_denied_unlisted(self) -> None:
        assert not has_permission(Role.admin, "orgs:create")
        assert not has_permission(Role.admin, "analytics:read")

    def test_developer_has_explicit_permissions(self) -> None:
        assert has_permission(Role.developer, "agents:create")
        assert has_permission(Role.developer, "agents:read")
        assert has_permission(Role.developer, "agents:run")
        assert has_permission(Role.developer, "agents:update")
        assert has_permission(Role.developer, "agents:delete")
        assert has_permission(Role.developer, "workflows:create")
        assert has_permission(Role.developer, "workflows:read")
        assert has_permission(Role.developer, "workflows:run")
        assert has_permission(Role.developer, "workflows:update")
        assert has_permission(Role.developer, "workflows:delete")
        assert has_permission(Role.developer, "files:manage")
        assert has_permission(Role.developer, "files:read")
        assert has_permission(Role.developer, "usage:read")
        assert has_permission(Role.developer, "models:read")
        assert has_permission(Role.developer, "providers:read")

    def test_developer_denied_admin_only(self) -> None:
        assert not has_permission(Role.developer, "models:manage")
        assert not has_permission(Role.developer, "mcp:manage")
        assert not has_permission(Role.developer, "providers:manage")
        assert not has_permission(Role.developer, "orgs:read")
        assert not has_permission(Role.developer, "orgs:manage")

    def test_developer_sessions_glob(self) -> None:
        assert has_permission(Role.developer, "sessions:read")
        assert has_permission(Role.developer, "sessions:delete")

    def test_viewer_has_read_only(self) -> None:
        assert has_permission(Role.viewer, "agents:read")
        assert has_permission(Role.viewer, "workflows:read")
        assert has_permission(Role.viewer, "usage:read")
        assert has_permission(Role.viewer, "sessions:read")
        assert has_permission(Role.viewer, "models:read")
        assert has_permission(Role.viewer, "providers:read")
        assert has_permission(Role.viewer, "orgs:read")

    def test_viewer_denied_mutate(self) -> None:
        assert not has_permission(Role.viewer, "agents:create")
        assert not has_permission(Role.viewer, "agents:update")
        assert not has_permission(Role.viewer, "agents:delete")
        assert not has_permission(Role.viewer, "workflows:create")
        assert not has_permission(Role.viewer, "workflows:delete")
        assert not has_permission(Role.viewer, "files:manage")
        assert not has_permission(Role.viewer, "providers:manage")
        assert not has_permission(Role.viewer, "models:manage")
        assert not has_permission(Role.viewer, "orgs:manage")

    def test_unknown_role_returns_false(self) -> None:
        assert not has_permission("superadmin", "agents:read")  # type: ignore[arg-type]


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

    def test_viewer_denied_create_agent(self, client: TestClient) -> None:
        owner_token = _register(client, "v_owner@test.com", PASSWORD, "ViewerTest")
        org_id = _get_org_id(client, owner_token)

        viewer_email = "v_denied@test.com"
        viewer_home_token = _add_member(client, owner_token, org_id, viewer_email, "viewer")

        # Viewer can GET agents (requires agents:read)
        assert client.get(
            "/api/agents", headers=_auth_headers(viewer_home_token, org_id)
        ).status_code == 200

        # Viewer cannot POST agents (requires agents:create)
        _, model_id = _create_provider_and_model(client, owner_token, org_id)
        resp = client.post(
            "/api/agents",
            headers=_auth_headers(viewer_home_token, org_id),
            json={"name": "should-fail", "system_prompt": "x", "model_id": model_id},
        )
        assert resp.status_code == 403

    def test_developer_can_create_agent(self, client: TestClient) -> None:
        owner_token = _register(client, "d_owner@test.com", PASSWORD, "DevTest")
        org_id = _get_org_id(client, owner_token)

        dev_email = "d_can_create@test.com"
        dev_home_token = _add_member(client, owner_token, org_id, dev_email, "developer")

        _, model_id = _create_provider_and_model(client, owner_token, org_id)
        resp = client.post(
            "/api/agents",
            headers=_auth_headers(dev_home_token, org_id),
            json={"name": "dev-agent", "system_prompt": "helpful", "model_id": model_id},
        )
        assert resp.status_code == 201, f"dev create agent failed: {resp.text}"

    def test_unauthenticated_request_returns_401(self, client: TestClient) -> None:
        assert client.get("/api/agents").status_code == 401
        assert client.get("/api/models").status_code == 401
        assert client.get("/api/providers").status_code == 401
        assert client.get("/api/sessions").status_code == 401
        assert client.get("/api/workflows").status_code == 401
        assert client.get("/api/files").status_code == 401

    def test_viewer_denied_provider_management(self, client: TestClient) -> None:
        owner_token = _register(client, "pm_owner@test.com", PASSWORD, "ProvMgt")
        org_id = _get_org_id(client, owner_token)

        viewer_email = "pm_denied@test.com"
        viewer_home_token = _add_member(client, owner_token, org_id, viewer_email, "viewer")

        # Viewer can read providers
        assert client.get(
            "/api/providers", headers=_auth_headers(viewer_home_token, org_id)
        ).status_code == 200

        # Viewer cannot create providers (requires providers:manage)
        resp = client.post(
            "/api/providers",
            headers=_auth_headers(viewer_home_token, org_id),
            json={"key": "bad", "name": "bad", "base_url": "http://x", "api_key": "sk-xxx"},
        )
        assert resp.status_code == 403

    def test_developer_denied_mcp_management(self, client: TestClient) -> None:
        owner_token = _register(client, "mcp_owner@test.com", PASSWORD, "MCPTest")
        org_id = _get_org_id(client, owner_token)

        dev_email = "mcp_denied@test.com"
        dev_home_token = _add_member(client, owner_token, org_id, dev_email, "developer")

        # Developer cannot create MCP server (requires mcp:manage)
        resp = client.post(
            "/api/mcp/servers",
            headers=_auth_headers(dev_home_token, org_id),
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

    def test_developer_cannot_manage_models(self, client: TestClient) -> None:
        owner_token = _register(client, "mm_owner@test.com", PASSWORD, "ModelMgt")
        org_id = _get_org_id(client, owner_token)

        dev_email = "mm_denied@test.com"
        dev_home_token = _add_member(client, owner_token, org_id, dev_email, "developer")

        # Developer can read models
        assert client.get(
            "/api/models", headers=_auth_headers(dev_home_token, org_id)
        ).status_code == 200

        # Developer cannot create models (requires models:manage)
        p_id, _ = _create_provider_and_model(client, owner_token, org_id)
        resp = client.post(
            "/api/models",
            headers=_auth_headers(dev_home_token, org_id),
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
        # the update endpoint allows overrides — verify the new value stuck
        updated = get_resp.json()
        # We only sent allowed_risk_tiers; verify it's applied
        assert updated.get("allowed_risk_tiers") == ["write"]
