from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.quota.dependencies import _redis_client
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.schemas.chat import AgentLoopResult, ChatRequest
from app.services.agent_service import AgentService
from app.services.chat_service import ChatService

PASSWORD = "Secret123!"


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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

    async def _override_redis():
        yield None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_redis_client] = _override_redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()



def _register(client: TestClient, email: str, org_name: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "org_name": org_name},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["memberships"][0]["org_id"]


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}


def _create_agent(client: TestClient, token: str, org_id: str) -> dict:
    headers = _headers(token, org_id)
    provider = client.post(
        "/api/providers",
        headers=headers,
        json={
            "key": "release-provider",
            "name": "Release Provider",
            "base_url": "http://localhost:9999/v1",
            "api_key": "test",
        },
    )
    assert provider.status_code == 201, provider.text
    model = client.post(
        "/api/models",
        headers=headers,
        json={
            "provider_id": provider.json()["id"],
            "name": "release-model",
            "display_name": "Release Model",
        },
    )
    assert model.status_code == 201, model.text
    agent = client.post(
        "/api/agents",
        headers=headers,
        json={
            "name": "Release Agent",
            "system_prompt": "version one",
            "model_id": model.json()["id"],
        },
    )
    assert agent.status_code == 201, agent.text
    return agent.json()


def test_release_draft_publish_and_rollback(client: TestClient) -> None:
    token, org_id = _register(client, "release-owner@example.com", "Release Org")
    headers = _headers(token, org_id)
    agent = _create_agent(client, token, org_id)

    assert agent["latest_release_number"] == 1
    assert agent["active_release_id"]

    initial = client.get(
        f"/api/agents/{agent['id']}/releases/1", headers=headers
    )
    assert initial.status_code == 200
    assert initial.json()["status"] == "published"
    assert initial.json()["system_prompt"] == "version one"

    draft = client.post(
        f"/api/agents/{agent['id']}/releases",
        headers=headers,
        json={"system_prompt": "version two", "change_note": "Improve policy"},
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["version"] == 2
    assert draft.json()["status"] == "draft"

    unchanged = client.get(f"/api/agents/{agent['id']}", headers=headers)
    assert unchanged.json()["system_prompt"] == "version one"
    assert unchanged.json()["active_release_id"] == agent["active_release_id"]

    # Create a failing evaluation run for draft release 2
    suite = client.post(
        "/api/evaluations/suites",
        headers=headers,
        json={"name": "Gate Suite", "agent_id": agent["id"]},
    ).json()
    case = client.post(
        f"/api/evaluations/suites/{suite['id']}/cases",
        headers=headers,
        json={"input": "test input", "expected_output": "correct output"},
    ).json()
    failed_run = client.post(
        f"/api/evaluations/suites/{suite['id']}/runs",
        headers=headers,
        json={
            "agent_release_id": draft.json()["id"],
            "execution_mode": "recorded",
            "recorded_outputs": [
                {"case_id": case["id"], "output": "wrong output"}
            ],
        },
    )
    assert failed_run.status_code == 201

    # Attempt to publish release 2 should fail quality gate
    fail_pub = client.post(
        f"/api/agents/{agent['id']}/releases/2/publish", headers=headers
    )
    # 409, not 400: the request is well-formed, the release state conflicts.
    # An owner may knowingly override it (see the force-publish tests).
    assert fail_pub.status_code == 409
    detail = fail_pub.json()["detail"]
    assert "failed quality gate" in detail["message"]
    assert detail["quality_gate_run_id"]
    assert detail["pass_rate"] < detail["min_pass_rate"]

    # Pass the quality gate by creating a successful run
    pass_run = client.post(
        f"/api/evaluations/suites/{suite['id']}/runs",
        headers=headers,
        json={
            "agent_release_id": draft.json()["id"],
            "execution_mode": "recorded",
            "recorded_outputs": [
                {"case_id": case["id"], "output": "correct output"}
            ],
        },
    )
    assert pass_run.status_code == 201

    published = client.post(
        f"/api/agents/{agent['id']}/releases/2/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    active = client.get(f"/api/agents/{agent['id']}", headers=headers).json()
    assert active["system_prompt"] == "version two"
    assert active["active_release_id"] == published.json()["id"]

    rollback = client.post(
        f"/api/agents/{agent['id']}/releases/1/rollback", headers=headers
    )
    assert rollback.status_code == 201, rollback.text
    assert rollback.json()["version"] == 3
    assert rollback.json()["system_prompt"] == "version one"
    assert rollback.json()["change_note"] == "Rollback to version 1"

    releases = client.get(
        f"/api/agents/{agent['id']}/releases", headers=headers
    ).json()
    assert [release["version"] for release in releases] == [3, 2, 1]
    assert [release["status"] for release in releases] == [
        "published",
        "archived",
        "archived",
    ]


def test_existing_update_auto_publishes_release(client: TestClient) -> None:
    token, org_id = _register(client, "release-update@example.com", "Update Org")
    headers = _headers(token, org_id)
    agent = _create_agent(client, token, org_id)

    updated = client.put(
        f"/api/agents/{agent['id']}",
        headers=headers,
        json={"system_prompt": "compatible update"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["latest_release_number"] == 2

    releases = client.get(
        f"/api/agents/{agent['id']}/releases", headers=headers
    ).json()
    assert releases[0]["status"] == "published"
    assert releases[0]["system_prompt"] == "compatible update"
    assert releases[1]["status"] == "archived"


def test_release_access_is_tenant_scoped(client: TestClient) -> None:
    owner_token, owner_org = _register(
        client, "release-tenant-owner@example.com", "Owner Org"
    )
    other_token, other_org = _register(
        client, "release-tenant-other@example.com", "Other Org"
    )
    agent = _create_agent(client, owner_token, owner_org)

    response = client.get(
        f"/api/agents/{agent['id']}/releases/1",
        headers=_headers(other_token, other_org),
    )
    assert response.status_code == 404
    create_response = client.post(
        f"/api/agents/{agent['id']}/releases",
        headers=_headers(other_token, other_org),
        json={"system_prompt": "cross-tenant draft"},
    )
    assert create_response.status_code == 404


def test_viewer_cannot_publish_release(client: TestClient) -> None:
    owner_token, org_id = _register(
        client, "release-rbac-owner@example.com", "RBAC Release Org"
    )
    agent = _create_agent(client, owner_token, org_id)
    viewer_token, _ = _register(
        client, "release-rbac-viewer@example.com", "Viewer Home"
    )
    add = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_headers(owner_token, org_id),
        json={"email": "release-rbac-viewer@example.com", "role": "viewer"},
    )
    assert add.status_code == 201, add.text

    response = client.post(
        f"/api/agents/{agent['id']}/releases/1/publish",
        headers=_headers(viewer_token, org_id),
    )
    assert response.status_code == 403


def _draft_with_failing_gate(client: TestClient, token: str, org_id: str) -> dict:
    """Create an agent whose draft release 2 has a red quality gate."""
    headers = _headers(token, org_id)
    agent = _create_agent(client, token, org_id)
    draft = client.post(
        f"/api/agents/{agent['id']}/releases",
        headers=headers,
        json={"system_prompt": "version two", "change_note": "regress"},
    ).json()
    suite = client.post(
        "/api/evaluations/suites",
        headers=headers,
        json={"name": "Force Gate Suite", "agent_id": agent["id"]},
    ).json()
    case = client.post(
        f"/api/evaluations/suites/{suite['id']}/cases",
        headers=headers,
        json={"input": "test input", "expected_output": "correct output"},
    ).json()
    run = client.post(
        f"/api/evaluations/suites/{suite['id']}/runs",
        headers=headers,
        json={
            "agent_release_id": draft["id"],
            "execution_mode": "recorded",
            "recorded_outputs": [{"case_id": case["id"], "output": "wrong output"}],
        },
    )
    assert run.status_code == 201, run.text
    return agent


def test_force_publish_requires_admin(client: TestClient) -> None:
    """A plain user has no publish rights at all in the 2-role model, so they
    can't reach a red gate to force-publish over it in the first place."""
    admin_token, org_id = _register(client, "force-owner@example.com", "Force Org")
    agent = _draft_with_failing_gate(client, admin_token, org_id)

    user_token, _ = _register(client, "force-dev@example.com", "Dev Home")
    add = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_headers(admin_token, org_id),
        json={"email": "force-dev@example.com", "role": "user"},
    )
    assert add.status_code == 201, add.text

    forced = client.post(
        f"/api/agents/{agent['id']}/releases/2/publish",
        headers=_headers(user_token, org_id),
        json={"force": True},
    )
    assert forced.status_code == 403
    assert "agents:publish" in forced.json()["detail"]


@pytest.mark.asyncio
async def test_owner_force_publish_records_override(
    client: TestClient, async_session_factory
) -> None:
    """Overriding a red gate must leave an explicit audit trail."""
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    token, org_id = _register(client, "force-audit@example.com", "Force Audit Org")
    headers = _headers(token, org_id)
    agent = _draft_with_failing_gate(client, token, org_id)

    blocked = client.post(f"/api/agents/{agent['id']}/releases/2/publish", headers=headers)
    assert blocked.status_code == 409

    forced = client.post(
        f"/api/agents/{agent['id']}/releases/2/publish",
        headers=headers,
        json={"force": True},
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["status"] == "published"
    # The verdict is retained, so "was this shipped over a red gate?" stays
    # answerable after the fact.
    assert forced.json().get("quality_gate_status") == "failed"

    async with async_session_factory() as db:
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.org_id == org_id,
                AuditLog.action == "agent.release.gate_overridden",
            )
        )
        overrides = list(result.scalars().all())

    assert len(overrides) == 1
    assert overrides[0].metadata_["version"] == 2
    assert overrides[0].metadata_["quality_gate_run_id"]


@pytest.mark.asyncio
async def test_session_pins_the_release_used_at_creation(
    client: TestClient, async_session_factory
) -> None:
    token, org_id = _register(client, "release-session@example.com", "Session Org")
    headers = _headers(token, org_id)
    agent = _create_agent(client, token, org_id)

    async with async_session_factory() as db:
        session = await ChatService(db).ensure_session(
            org_id,
            ChatRequest(
                agent_id=agent["id"],
                message="start pinned session",
                stream=False,
            ),
        )
        pinned_release_id = session.agent_release_id

    draft = client.post(
        f"/api/agents/{agent['id']}/releases",
        headers=headers,
        json={"system_prompt": "new active prompt"},
    )
    assert draft.status_code == 201
    publish = client.post(
        f"/api/agents/{agent['id']}/releases/2/publish", headers=headers
    )
    assert publish.status_code == 200

    async with async_session_factory() as db:
        runtime = await AgentService(db).runtime_agent(
            org_id, agent["id"], pinned_release_id
        )
        assert runtime.system_prompt == "version one"
        assert runtime.active_release_id == pinned_release_id


def test_model_update_becomes_default_for_new_chat_session(
    client: TestClient, async_session_factory
) -> None:
    token, org_id = _register(client, "release-model-default@example.com", "Model Default Org")
    headers = _headers(token, org_id)
    agent = _create_agent(client, token, org_id)

    provider_id = client.get("/api/providers", headers=headers).json()[0]["id"]
    alternate = client.post(
        "/api/models",
        headers=headers,
        json={
            "provider_id": provider_id,
            "name": "alternate-model",
            "display_name": "Alternate Model",
        },
    )
    assert alternate.status_code == 201, alternate.text

    updated = client.put(
        f"/api/agents/{agent['id']}",
        headers=headers,
        json={"model_id": alternate.json()["id"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["model_id"] == alternate.json()["id"]
    assert updated.json()["latest_release_number"] == 2

    async def _new_session_model() -> tuple[str | None, str | None]:
        async with async_session_factory() as db:
            service = ChatService(db)
            session = await service.ensure_session(
                org_id,
                ChatRequest(agent_id=agent["id"], message="use new default", stream=False),
            )
            runtime = await AgentService(db).runtime_agent(
                org_id, agent["id"], session.agent_release_id
            )
            return session.agent_release_id, runtime.model_id

    import anyio

    release_id, session_model_id = anyio.run(_new_session_model)
    assert release_id == updated.json()["active_release_id"]
    assert session_model_id == alternate.json()["id"]


def test_model_selection_repins_only_the_current_chat_session(
    client: TestClient, async_session_factory
) -> None:
    token, org_id = _register(client, "release-model-repin@example.com", "Model Repin Org")
    headers = _headers(token, org_id)
    agent = _create_agent(client, token, org_id)

    provider_id = client.get("/api/providers", headers=headers).json()[0]["id"]
    alternate = client.post(
        "/api/models",
        headers=headers,
        json={
            "provider_id": provider_id,
            "name": "repin-model",
            "display_name": "Repin Model",
        },
    )
    assert alternate.status_code == 201, alternate.text

    async def _create_sessions() -> tuple[str, str, str | None]:
        async with async_session_factory() as db:
            service = ChatService(db)
            current = await service.ensure_session(
                org_id, ChatRequest(agent_id=agent["id"], message="current", stream=False)
            )
            other = await service.ensure_session(
                org_id, ChatRequest(agent_id=agent["id"], message="other", stream=False)
            )
            return current.id, other.id, current.agent_release_id

    import anyio

    current_id, other_id, original_release_id = anyio.run(_create_sessions)
    updated = client.put(
        f"/api/agents/{agent['id']}",
        headers=headers,
        json={"model_id": alternate.json()["id"]},
    )
    assert updated.status_code == 200, updated.text

    async def _repin_current_session() -> tuple[str | None, str | None, str | None]:
        async with async_session_factory() as db:
            service = ChatService(db)
            current = await service.ensure_session(
                org_id,
                ChatRequest(
                    agent_id=agent["id"],
                    message="continue with selected model",
                    session_id=current_id,
                    # Browser state may lag the Agent query refetch. This is
                    # an apply-default signal, not a second model assertion.
                    model_id="stale-browser-model-id",
                    stream=False,
                ),
            )
            other = await service.ensure_session(
                org_id,
                ChatRequest(
                    agent_id=agent["id"], message="continue unchanged", session_id=other_id, stream=False
                ),
            )
            runtime = await AgentService(db).runtime_agent(
                org_id, agent["id"], current.agent_release_id
            )
            return current.agent_release_id, other.agent_release_id, runtime.model_id

    current_release_id, other_release_id, current_model_id = anyio.run(_repin_current_session)
    assert current_release_id == updated.json()["active_release_id"]
    assert current_release_id != original_release_id
    assert current_model_id == alternate.json()["id"]
    assert other_release_id == original_release_id


def test_user_model_selection_is_per_chat_and_validated(
    client: TestClient, async_session_factory, monkeypatch
) -> None:
    admin_token, org_id = _register(client, "user-model-admin@example.com", "User Model Org")
    admin_headers = _headers(admin_token, org_id)
    agent = _create_agent(client, admin_token, org_id)
    provider_id = client.get("/api/providers", headers=admin_headers).json()[0]["id"]
    alternate = client.post(
        "/api/models",
        headers=admin_headers,
        json={
            "provider_id": provider_id,
            "name": "user-selectable-model",
            "display_name": "User Selectable Model",
        },
    )
    assert alternate.status_code == 201, alternate.text
    alternate_id = alternate.json()["id"]

    user_email = "user-model-consumer@example.com"
    user_token, _user_org = _register(client, user_email, "User Home")
    profile = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {user_token}"}
    ).json()
    invited = client.post(
        f"/api/orgs/{org_id}/members",
        headers=admin_headers,
        json={"email": user_email, "role": "user"},
    )
    assert invited.status_code == 201, invited.text

    captured: dict[str, str | None] = {}

    async def fake_run_agent_loop(*_args, **kwargs) -> AgentLoopResult:
        captured["model_id"] = kwargs["model_id"]
        return AgentLoopResult(content="ok")

    monkeypatch.setattr("app.services.chat_service.run_agent_loop", fake_run_agent_loop)

    async def _run_selected_model() -> AgentLoopResult:
        async with async_session_factory() as db:
            return await ChatService(db).run(
                org_id,
                ChatRequest(
                    agent_id=agent["id"],
                    model_id=alternate_id,
                    message="use selected model",
                    stream=False,
                ),
                user_id=profile["id"],
                user_role="user",
            )

    import anyio

    result = anyio.run(_run_selected_model)
    assert result.content == "ok"
    assert captured["model_id"] == alternate_id

    inactive = client.put(
        f"/api/models/{alternate_id}",
        headers=admin_headers,
        json={"active": False},
    )
    assert inactive.status_code == 200, inactive.text

    _other_token, other_org = _register(client, "other-model-org@example.com", "Other Model Org")
    other_agent = _create_agent(client, _other_token, other_org)
    cross_org_model_id = other_agent["model_id"]

    async def _run_unavailable_model() -> None:
        async with async_session_factory() as db:
            with pytest.raises(ValueError, match="not available"):
                await ChatService(db).run(
                    org_id,
                    ChatRequest(
                        agent_id=agent["id"],
                        model_id=alternate_id,
                        message="reject inactive model",
                        stream=False,
                    ),
                    user_id=profile["id"],
                    user_role="user",
                )

    anyio.run(_run_unavailable_model)

    async def _run_cross_org_model() -> None:
        async with async_session_factory() as db:
            with pytest.raises(ValueError, match="not available"):
                await ChatService(db).run(
                    org_id,
                    ChatRequest(
                        agent_id=agent["id"],
                        model_id=cross_org_model_id,
                        message="reject cross-org model",
                        stream=False,
                    ),
                    user_id=profile["id"],
                    user_role="user",
                )

    anyio.run(_run_cross_org_model)
