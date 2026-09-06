from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.quota.dependencies import _redis_client
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.agent import Agent
from app.models.approval_request import ApprovalRequest
from app.models.files import UploadedFile
from app.models.message import Message
from app.models.session import Session
from app.models.task import Task
from app.models.usage import UsageEvent
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.models.workspace import SandboxExecution, WorkspaceArtifact

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


def _register(client: TestClient, email: str, org_name: str) -> tuple[str, str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "org_name": org_name},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    profile = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).json()
    return token, profile["memberships"][0]["org_id"], profile["id"]


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}


def test_user_reads_only_owned_workspace_approvals_and_quota_usage(
    client: TestClient, async_session_factory
) -> None:
    admin_token, org_id, admin_id = _register(
        client, "scope-admin@example.com", "Scoped Org"
    )
    user_token, _home_org, user_id = _register(
        client, "scope-user@example.com", "User Home"
    )
    invited = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_headers(admin_token, org_id),
        json={"email": "scope-user@example.com", "role": "user"},
    )
    assert invited.status_code == 201, invited.text

    async def _seed() -> None:
        async with async_session_factory() as db:
            db.add_all(
                [
                    WorkspaceArtifact(
                        org_id=org_id,
                        created_by_user_id=admin_id,
                        path="admin.txt",
                    ),
                    WorkspaceArtifact(
                        org_id=org_id,
                        created_by_user_id=user_id,
                        path="user.txt",
                    ),
                    SandboxExecution(
                        org_id=org_id,
                        created_by_user_id=admin_id,
                        source="test",
                        command="admin",
                    ),
                    SandboxExecution(
                        org_id=org_id,
                        created_by_user_id=user_id,
                        source="test",
                        command="user",
                    ),
                    ApprovalRequest(
                        org_id=org_id,
                        run_type="agent",
                        requested_by=admin_id,
                        status="pending",
                    ),
                    ApprovalRequest(
                        org_id=org_id,
                        run_type="agent",
                        requested_by=user_id,
                        status="pending",
                    ),
                    UsageEvent(
                        org_id=org_id,
                        created_by_user_id=admin_id,
                        source="chat",
                        cost_usd=9,
                    ),
                    UsageEvent(
                        org_id=org_id,
                        created_by_user_id=user_id,
                        source="chat",
                        cost_usd=2,
                    ),
                    Agent(
                        org_id=org_id,
                        created_by_user_id=admin_id,
                        name="Admin agent",
                    ),
                    Agent(
                        org_id=org_id,
                        created_by_user_id=user_id,
                        name="User agent",
                    ),
                    Workflow(
                        org_id=org_id,
                        created_by_user_id=admin_id,
                        name="Admin workflow",
                    ),
                    Workflow(
                        org_id=org_id,
                        created_by_user_id=user_id,
                        name="User workflow",
                    ),
                    UploadedFile(
                        org_id=org_id,
                        created_by_user_id=admin_id,
                        filename="admin.txt",
                        original_name="admin.txt",
                        stored_path="admin.txt",
                        size=10,
                    ),
                    UploadedFile(
                        org_id=org_id,
                        created_by_user_id=user_id,
                        filename="user.txt",
                        original_name="user.txt",
                        stored_path="user.txt",
                        size=20,
                    ),
                ]
            )
            await db.commit()

    import anyio

    anyio.run(_seed)

    user_headers = _headers(user_token, org_id)
    artifacts = client.get("/api/workspace/artifacts", headers=user_headers)
    assert artifacts.status_code == 200, artifacts.text
    assert [item["path"] for item in artifacts.json()] == ["user.txt"]

    executions = client.get("/api/workspace/executions", headers=user_headers)
    assert executions.status_code == 200, executions.text
    assert [item["command"] for item in executions.json()] == ["user"]

    approvals = client.get("/api/approvals?include_chat=true", headers=user_headers)
    assert approvals.status_code == 200, approvals.text
    assert len(approvals.json()) == 1
    assert approvals.json()[0]["requested_by"] == user_id

    usage = client.get(f"/api/orgs/{org_id}/quota/usage", headers=user_headers)
    assert usage.status_code == 200, usage.text
    assert usage.json()["monthly_cost_usd"] == 2
    assert usage.json()["agents"] == 1
    assert usage.json()["workflows"] == 1
    assert usage.json()["storage_bytes"] == 20
    assert usage.json()["active_run_leases"] == 0

    admin_usage = client.get(
        f"/api/orgs/{org_id}/quota/usage", headers=_headers(admin_token, org_id)
    )
    assert admin_usage.status_code == 200, admin_usage.text
    assert admin_usage.json()["monthly_cost_usd"] == 11
    assert admin_usage.json()["agents"] == 2
    assert admin_usage.json()["workflows"] == 2
    assert admin_usage.json()["storage_bytes"] == 30


def test_user_cannot_read_other_users_sessions_or_runs(
    client: TestClient, async_session_factory
) -> None:
    admin_token, org_id, admin_id = _register(
        client, "scope-runs-admin@example.com", "Scoped Runs"
    )
    user_token, _home_org, user_id = _register(
        client, "scope-runs-user@example.com", "User Runs Home"
    )
    invited = client.post(
        f"/api/orgs/{org_id}/members",
        headers=_headers(admin_token, org_id),
        json={"email": "scope-runs-user@example.com", "role": "user"},
    )
    assert invited.status_code == 201, invited.text

    async def _seed() -> tuple[str, str, str, str]:
        async with async_session_factory() as db:
            admin_agent = Agent(org_id=org_id, created_by_user_id=admin_id, name="Run agent")
            workflow = Workflow(
                org_id=org_id, created_by_user_id=admin_id, name="Run workflow"
            )
            db.add_all([admin_agent, workflow])
            await db.flush()
            admin_session = Session(
                org_id=org_id,
                created_by_user_id=admin_id,
                agent_id=admin_agent.id,
                title="Admin session",
            )
            user_session = Session(
                org_id=org_id,
                created_by_user_id=user_id,
                agent_id=admin_agent.id,
                title="User session",
            )
            db.add_all([admin_session, user_session])
            await db.flush()
            db.add_all(
                [
                    Message(
                        org_id=org_id,
                        session_id=admin_session.id,
                        created_by_user_id=admin_id,
                        role="user",
                        content="admin secret",
                        position=1,
                    ),
                    Message(
                        org_id=org_id,
                        session_id=user_session.id,
                        created_by_user_id=user_id,
                        role="user",
                        content="user message",
                        position=1,
                    ),
                    Task(
                        org_id=org_id,
                        root_run_id="admin-chat-run",
                        agent_id=admin_agent.id,
                        goal="admin run",
                        status="succeeded",
                        triggered_by_user_id=admin_id,
                    ),
                    Task(
                        org_id=org_id,
                        root_run_id="user-chat-run",
                        agent_id=admin_agent.id,
                        goal="user run",
                        status="succeeded",
                        triggered_by_user_id=user_id,
                    ),
                    WorkflowRun(
                        id="admin-workflow-run",
                        org_id=org_id,
                        workflow_id=workflow.id,
                        triggered_by_user_id=admin_id,
                        status="succeeded",
                    ),
                    WorkflowRun(
                        id="user-workflow-run",
                        org_id=org_id,
                        workflow_id=workflow.id,
                        triggered_by_user_id=user_id,
                        status="succeeded",
                    ),
                ]
            )
            await db.commit()
            return admin_session.id, user_session.id, workflow.id, admin_agent.id

    import anyio

    admin_session_id, user_session_id, _workflow_id, _agent_id = anyio.run(_seed)
    user_headers = _headers(user_token, org_id)

    sessions = client.get("/api/sessions", headers=user_headers)
    assert sessions.status_code == 200, sessions.text
    assert [row["id"] for row in sessions.json()] == [user_session_id]

    own_messages = client.get(
        f"/api/sessions/{user_session_id}/messages", headers=user_headers
    )
    assert own_messages.status_code == 200, own_messages.text
    assert own_messages.json()[0]["content"] == "user message"

    other_messages = client.get(
        f"/api/sessions/{admin_session_id}/messages", headers=user_headers
    )
    assert other_messages.status_code == 404, other_messages.text

    assert client.get("/api/chat/runs/user-chat-run", headers=user_headers).status_code == 200
    assert client.get("/api/chat/runs/admin-chat-run", headers=user_headers).status_code == 404
    assert client.get(
        "/api/workflows/runs/user-workflow-run", headers=user_headers
    ).status_code == 200
    assert client.get(
        "/api/workflows/runs/admin-workflow-run", headers=user_headers
    ).status_code == 404

    user_list = client.get("/api/workflows/runs", headers=user_headers)
    assert user_list.status_code == 200, user_list.text
    assert [row["id"] for row in user_list.json()] == ["user-workflow-run"]

    admin_list = client.get("/api/workflows/runs", headers=_headers(admin_token, org_id))
    assert admin_list.status_code == 200, admin_list.text
    assert {row["id"] for row in admin_list.json()} == {"admin-workflow-run", "user-workflow-run"}
