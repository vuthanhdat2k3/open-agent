"""An approval decision must never let the *approver's* identity leak into
the resumed run's execution context.

Root cause this guards against: `decide_approval` builds the resume payload
from `task.execution_principal` - the snapshot taken when the run was first
created - specifically so that whichever admin clicks "approve" cannot
accidentally (or by a future refactor reading `current_user` instead)
become the principal the resumed tool call executes as. That distinction
matters for authorization (an admin approving a user's request must not
grant the resumed run the admin's own permissions) and for audit fidelity
(the audit trail must still show the original requester as the actor, and
`decided_by` as the separate, distinct approver).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.guardrails.approval import request_approval
from app.db.base import Base, utc_now
from app.db.session import get_db
from app.main import app
from app.models.agent import Agent
from app.models.approval_request import ApprovalRequest
from app.models.model import Model
from app.models.provider import Provider
from app.models.session import Session
from app.models.task import Task


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
        json={"email": email, "password": "Secret123!", "org_name": "PrincipalOrg"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["memberships"][0]["org_id"]


def _add_admin(client: TestClient, owner_token: str, org_id: str, email: str) -> str:
    """Register *email* and add them as an org_admin, return their token."""
    member_token, _ = _register(client, email)
    resp = client.post(
        f"/api/orgs/{org_id}/members",
        json={"email": email, "role": "org_admin"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 201, f"add admin failed: {resp.text}"
    return member_token


def test_decide_approval_resumes_with_the_original_requesters_principal(
    client: TestClient, async_session_factory
) -> None:
    """A distinct org_admin decides an approval that a regular user's chat
    run raised. The resume payload must carry the *requester's* user_id and
    role, not the deciding admin's - and `decided_by` on the approval row
    must be the admin, never silently overwritten with the requester."""
    requester_token, org_id = _register(client, "requester@test.com")
    approver_token = _add_admin(client, requester_token, org_id, "approver-admin@test.com")

    # Resolve each principal's own user id via /api/auth/me so the test does
    # not have to reach into JWT internals.
    requester_id = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {requester_token}"}
    ).json()["id"]
    approver_id = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {approver_token}"}
    ).json()["id"]
    assert requester_id != approver_id, "test requires two distinct principals"

    async def _seed() -> tuple[str, str, str, str]:
        async with async_session_factory() as session:
            provider = Provider(
                org_id=org_id, name="OpenAI", key="openai", base_url="http://x", api_key="k"
            )
            session.add(provider)
            await session.commit()
            await session.refresh(provider)

            model = Model(
                org_id=org_id, provider_id=provider.id, name="gpt-4o-mini", display_name="GPT-4o mini"
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)

            agent = Agent(org_id=org_id, name="assistant", model_id=model.id, tools=[])
            session.add(agent)
            await session.commit()
            await session.refresh(agent)

            chat_session = Session(
                org_id=org_id, agent_id=agent.id, agent_release_id=None, title="Requester's chat"
            )
            session.add(chat_session)
            await session.commit()
            await session.refresh(chat_session)

            # The root task's execution_principal snapshot reflects who
            # actually started the run - the requester, never the admin who
            # will later decide the approval.
            root_task = Task(
                id="root-task-principal",
                org_id=org_id,
                parent_task_id=None,
                root_run_id="root-task-principal",
                agent_id=agent.id,
                depth=0,
                triggered_by_user_id=requester_id,
                execution_principal={
                    "principal_type": "human",
                    "principal_id": requester_id,
                    "user_id": requester_id,
                    "role": "user",
                },
                goal="send the requester's email",
                status="waiting_approval",
                progress={
                    "session_id": chat_session.id,
                    "phase": "waiting_approval",
                    "model_id": model.id,
                },
                created_at=utc_now(),
            )
            session.add(root_task)
            await session.commit()

            approval = await request_approval(
                session,
                org_id=org_id,
                run_type="agent",
                run_id=root_task.root_run_id,
                tool_name="email_send",
                args_snapshot={"draft_id": "d-1"},
                requested_by=requester_id,
                owning_task_id=root_task.id,
            )
            return approval.id, chat_session.id, agent.id, model.id

    import anyio

    approval_id, chat_session_id, agent_id, model_id = anyio.run(_seed)
    approver_headers = {"Authorization": f"Bearer {approver_token}", "X-Org-Id": org_id}

    with patch("app.api.v1.routes.approvals.run_chat_detached", new=AsyncMock()) as mock_resume:
        decided = client.post(
            f"/api/approvals/{approval_id}/decide",
            headers=approver_headers,
            json={"decision": "approved", "reason": "looks fine"},
        )
        assert decided.status_code == 200, decided.text

    # The approval row must record the approver as decided_by ...
    assert decided.json()["decided_by"] == approver_id

    # ... but the resumed run's execution context must stay the requester's,
    # not the approver's.
    assert mock_resume.await_count == 1
    payload = mock_resume.await_args.args[0]
    assert payload["user_id"] == requester_id, (
        "the resumed run must execute as the original requester, not the "
        f"deciding approver (payload was: {payload!r})"
    )
    assert payload["user_role"] == "user"
    assert payload["session_id"] == chat_session_id
    assert payload["agent_id"] == agent_id
    assert payload["model_id"] == model_id


async def test_approval_row_never_conflates_requested_by_and_decided_by(
    async_session_factory,
) -> None:
    """Direct model-level check: resolve_approval only ever writes
    decided_by, and must not also mutate requested_by to match it."""
    from app.core.guardrails.approval import resolve_approval

    async with async_session_factory() as db:
        from app.models.organization import Organization

        org = Organization(name="Decide Org", slug="decide-org")
        db.add(org)
        await db.commit()
        await db.refresh(org)

        approval = await request_approval(
            db,
            org_id=org.id,
            run_type="agent",
            run_id="run-1",
            tool_name="email_send",
            args_snapshot={},
            requested_by="user-requester",
        )
        resolved = await resolve_approval(
            db,
            approval_id=approval.id,
            org_id=org.id,
            decision="approved",
            decided_by="user-approver",
            reason="ok",
        )

        refreshed = await db.scalar(
            select(ApprovalRequest).where(ApprovalRequest.id == approval.id)
        )

    assert resolved is not None
    assert refreshed.requested_by == "user-requester"
    assert refreshed.decided_by == "user-approver"
    assert refreshed.requested_by != refreshed.decided_by
