"""Tests for the PATCH member-role endpoint and the force-change-password flow.

Covers:
- ``PATCH /api/orgs/{id}/members/{user_id}`` happy path + every guard.
- ``must_change_password`` flag is set on invite and cleared by ``PATCH /me``.
- ``/api/workflows/node-options?type=users`` denies plain ``user`` members
  (member-email PII protection).
- ``/api/workflow-catalog/publish`` no longer rejects ``org_admin``/``platform_admin``
  (regression for the operator-only role check that excluded admins).
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User

PASSWORD = "Secret123!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _force_local_auth_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Other tests may have side effects that let the project's parent
    ``.env`` leak into this test's Settings (the project ships
    ``OPENAGENT_AUTH_PROVIDER=zitadel`` there). Force the local provider
    so the legacy auth surface used here stays available, and clear the
    cached Settings to pick up the new value.
    """
    monkeypatch.setenv("OPENAGENT_AUTH_PROVIDER", "local")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
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
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str, password: str = PASSWORD, org_name: str | None = None) -> str:
    body: dict[str, Any] = {"email": email, "password": password}
    if org_name:
        body["org_name"] = org_name
    resp = client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, f"register failed: {resp.text}"
    return resp.json()["access_token"]


def _me(client: TestClient, token: str) -> dict[str, Any]:
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _org_id(client: TestClient, token: str) -> str:
    return _me(client, token)["memberships"][0]["org_id"]


def _add_member(client: TestClient, token: str, org_id: str, email: str, role: str) -> dict[str, Any]:
    resp = client.post(
        f"/api/orgs/{org_id}/members",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"add member failed: {resp.text}"
    return resp.json()


def _login_token(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _mint_platform_admin_token(async_session_factory) -> str:
    """Granting org_admin is platform_admin-only; local auth has no API path
    to become platform_admin, so insert one directly. Its break-glass access
    to any tenant org needs no membership row there (see
    dependencies.py::_global_platform_admin_roles)."""
    import asyncio
    import uuid

    from app.core.auth.jwt import create_access_token

    async def _setup() -> str:
        async with async_session_factory() as session:
            org = Organization(name="Platform", slug=f"platform-{uuid.uuid4().hex[:8]}")
            session.add(org)
            await session.flush()
            user = User(
                email=f"pa-{uuid.uuid4().hex[:8]}@test.com",
                display_name="Platform Admin",
                hashed_password="x",
            )
            session.add(user)
            await session.flush()
            session.add(Membership(org_id=org.id, user_id=user.id, role=Role.platform_admin))
            await session.commit()
            return create_access_token(user_id=user.id, org_id=org.id, role="platform_admin")

    return asyncio.run(_setup())


def _patch_role(client: TestClient, token: str, org_id: str, user_id: str, role: str) -> Any:
    return client.patch(
        f"/api/orgs/{org_id}/members/{user_id}",
        json={"role": role},
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# PATCH role endpoint
# ---------------------------------------------------------------------------


class TestPatchMemberRole:
    def test_org_admin_can_promote_user_to_operator(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_p@test.com", PASSWORD, "Org Promote")
        org_id = _org_id(client, admin_token)
        member = _add_member(client, admin_token, org_id, "promote_target@test.com", "user")

        resp = _patch_role(client, admin_token, org_id, member["user_id"], "operator")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["role"] == "operator"
        assert body["user_id"] == member["user_id"]

    def test_operator_cannot_change_roles(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_op2@test.com", PASSWORD, "Org OpTest")
        org_id = _org_id(client, admin_token)
        _add_member(client, admin_token, org_id, "opt@test.com", "operator")
        target = _add_member(client, admin_token, org_id, "opt_target@test.com", "user")

        op_token = _login_token(client, "opt@test.com", "OpenAgent@2026")
        resp = _patch_role(client, op_token, org_id, target["user_id"], "operator")
        assert resp.status_code == 403, resp.text

    def test_user_cannot_change_roles(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_u@test.com", PASSWORD, "Org UserTest")
        org_id = _org_id(client, admin_token)
        _add_member(client, admin_token, org_id, "u1@test.com", "user")
        target = _add_member(client, admin_token, org_id, "u2@test.com", "user")

        user_token = _login_token(client, "u1@test.com", "OpenAgent@2026")
        resp = _patch_role(client, user_token, org_id, target["user_id"], "operator")
        assert resp.status_code == 403, resp.text

    def test_cannot_change_own_role(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_self@test.com", PASSWORD, "Org Self")
        org_id = _org_id(client, admin_token)
        admin_user_id = _me(client, admin_token)["id"]

        resp = _patch_role(client, admin_token, org_id, admin_user_id, "user")
        assert resp.status_code == 400, resp.text
        assert "own role" in resp.text

    def test_cannot_demote_last_org_admin(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_last@test.com", PASSWORD, "Org Last")
        org_id = _org_id(client, admin_token)
        admin_user_id = _me(client, admin_token)["id"]

        # The creator is the only org_admin; the endpoint must reject with
        # 400 (either "own role" or "last org_admin" guard applies and the
        # first one wins).
        resp = _patch_role(client, admin_token, org_id, admin_user_id, "user")
        assert resp.status_code == 400, resp.text
        assert "own role" in resp.text or "last org_admin" in resp.text

    def test_platform_admin_role_string_rejected_by_allowlist(self, client: TestClient) -> None:
        """``platform_admin`` is not a valid input value (the static allowlist
        only exposes ``org_admin|operator|user``); the guard for actual
        platform_admin memberships is covered by the org_admin-only fixture."""
        admin_token = _register(client, "admin_inv2@test.com", PASSWORD, "Org InvRole")
        org_id = _org_id(client, admin_token)
        member = _add_member(client, admin_token, org_id, "inv2@test.com", "user")

        resp = _patch_role(client, admin_token, org_id, member["user_id"], "platform_admin")
        assert resp.status_code == 400, resp.text

    def test_invalid_role_rejected(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_inv3@test.com", PASSWORD, "Org InvRole3")
        org_id = _org_id(client, admin_token)
        member = _add_member(client, admin_token, org_id, "inv3@test.com", "user")

        resp = _patch_role(client, admin_token, org_id, member["user_id"], "superuser")
        assert resp.status_code == 400, resp.text

    def test_org_admin_cannot_grant_org_admin_via_patch(self, client: TestClient) -> None:
        """Granting org_admin is platform_admin-only now - PATCH (the org's
        own org_admin job) no longer accepts "org_admin" as a target role at
        all; use POST /members with a platform_admin token instead."""
        admin_token = _register(client, "admin_pa@test.com", PASSWORD, "Org PromA")
        org_id = _org_id(client, admin_token)
        member = _add_member(client, admin_token, org_id, "promo@test.com", "operator")

        resp = _patch_role(client, admin_token, org_id, member["user_id"], "org_admin")
        assert resp.status_code == 400, resp.text

    def test_platform_admin_grants_org_admin_alongside_existing_role(
        self, client: TestClient, async_session_factory
    ) -> None:
        """Granting org_admin adds it alongside the member's existing
        functional role (operator/user) rather than replacing it - a member
        can hold both, like the self-registered founder does."""
        admin_token = _register(client, "admin_dem@test.com", PASSWORD, "Org Dem")
        org_id = _org_id(client, admin_token)
        member = _add_member(client, admin_token, org_id, "dem@test.com", "operator")

        platform_admin_token = _mint_platform_admin_token(async_session_factory)
        promote = client.post(
            f"/api/orgs/{org_id}/members",
            json={"email": "dem@test.com", "role": "org_admin"},
            headers={"Authorization": f"Bearer {platform_admin_token}"},
        )
        assert promote.status_code == 201, promote.text

        # The functional (operator) role is untouched by the grant; PATCH
        # still targets it, independent of the separately-held org_admin row.
        resp = _patch_role(client, admin_token, org_id, member["user_id"], "user")
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "user"


# ---------------------------------------------------------------------------
# Force-change-password flow
# ---------------------------------------------------------------------------


class TestForceChangePassword:
    def test_invite_sets_must_change_password(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_fcp@test.com", PASSWORD, "Org FCP")
        org_id = _org_id(client, admin_token)
        _add_member(client, admin_token, org_id, "invitee_fcp@test.com", "user")

        invited_token = _login_token(client, "invitee_fcp@test.com", "OpenAgent@2026")
        me = _me(client, invited_token)
        assert me["must_change_password"] is True

    def test_self_password_change_clears_flag(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_clear@test.com", PASSWORD, "Org Clear")
        org_id = _org_id(client, admin_token)
        _add_member(client, admin_token, org_id, "clear_flag@test.com", "user")

        invited_token = _login_token(client, "clear_flag@test.com", "OpenAgent@2026")
        assert _me(client, invited_token)["must_change_password"] is True

        resp = client.patch(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {invited_token}"},
            json={"old_password": "OpenAgent@2026", "new_password": PASSWORD},
        )
        assert resp.status_code == 200, resp.text
        me = _me(client, invited_token)
        assert me["must_change_password"] is False


# ---------------------------------------------------------------------------
# Node-options users gate (member-email PII)
# ---------------------------------------------------------------------------


class TestNodeOptionsUsersGate:
    def test_user_role_cannot_enumerate_users(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_no@test.com", PASSWORD, "Org NO")
        org_id = _org_id(client, admin_token)
        _add_member(client, admin_token, org_id, "no_user@test.com", "user")
        user_token = _login_token(client, "no_user@test.com", "OpenAgent@2026")

        resp = client.get(
            "/api/workflows/node-options?type=users",
            headers={"Authorization": f"Bearer {user_token}", "X-Org-Id": org_id},
        )
        assert resp.status_code == 403, resp.text

    def test_admin_can_list_users(self, client: TestClient) -> None:
        admin_token = _register(client, "admin_ls@test.com", PASSWORD, "Org LS")
        org_id = _org_id(client, admin_token)
        resp = client.get(
            "/api/workflows/node-options?type=users",
            headers={"Authorization": f"Bearer {admin_token}", "X-Org-Id": org_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert any(item["value"] for item in body)


# ---------------------------------------------------------------------------
# Catalog publish: org_admin must reach the "not found" path (not operator guard)
# ---------------------------------------------------------------------------


class TestCatalogPublishAdminAllowed:
    def test_org_admin_reaches_not_found_path(self, client: TestClient) -> None:
        """Regression: the publish endpoint used to gate on ``role !=
        operator`` which excluded org_admin/platform_admin. With the new
        ``principal.allows("workflows:manage")`` guard, an org_admin request
        for a missing workflow now hits 404 (not 403)."""
        admin_token = _register(client, "admin_pub@test.com", PASSWORD, "Org Pub")
        org_id = _org_id(client, admin_token)
        resp = client.post(
            "/api/workflow-catalog/publish",
            headers={"Authorization": f"Bearer {admin_token}", "X-Org-Id": org_id},
            json={"workflow_id": "wf-missing"},
        )
        assert resp.status_code == 404, resp.text
