"""Approving a delegated approval must resume the *same* chat session the
user is looking at, not a disconnected new one.

Root cause this guards against: `decide_approval` used to build the resume
payload with `"session_id": None`, and `ChatService.ensure_session` always
creates a brand-new `Session` row whenever `request.session_id` is falsy.
Every approval round-trip therefore fragmented one conversation across
multiple sessions - the root task's final answer landed in a session the
chat UI was not displaying, so users watching the original conversation saw
their message and then nothing: the reply "disappeared".

The root task the approval resumes (looked up by `root_run_id`) is always
the *root* task, so its `agent_id` never differs from the session's
`agent_id` across any number of delegated sub-agent hops - reusing
`task.progress["session_id"]` can never trip the "session belongs to a
different agent" guard in `ensure_session`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.guardrails.approval import request_approval
from app.db.base import Base, utc_now
from app.db.session import get_db
from app.main import app
from app.models.agent import Agent
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
        json={"email": email, "password": "Secret123!", "org_name": "ApprovalResumeOrg"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["memberships"][0]["org_id"]


def test_decide_approval_resumes_the_root_chat_session(
    client: TestClient, async_session_factory
) -> None:
    token, org_id = _register(client, "resume-owner@test.com")

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
                org_id=org_id, agent_id=agent.id, agent_release_id=None, title="Original conversation"
            )
            session.add(chat_session)
            await session.commit()
            await session.refresh(chat_session)

            root_task = Task(
                id="root-task-1",
                org_id=org_id,
                parent_task_id=None,
                root_run_id="root-task-1",
                agent_id=agent.id,
                depth=0,
                goal="send the farewell email",
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
                requested_by=None,
                owning_task_id=root_task.id,
            )
            return approval.id, chat_session.id, agent.id, model.id

    import anyio

    approval_id, chat_session_id, agent_id, model_id = anyio.run(_seed)
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    with patch("app.api.v1.routes.approvals.run_chat_detached", new=AsyncMock()) as mock_resume:
        decided = client.post(
            f"/api/approvals/{approval_id}/decide",
            headers=headers,
            json={"decision": "approved", "reason": ""},
        )
        assert decided.status_code == 200, decided.text

    assert mock_resume.await_count == 1
    payload = mock_resume.await_args.args[0]
    assert payload["session_id"] == chat_session_id, (
        f"resume must reuse the root task's own chat session, not create a "
        f"disconnected new one (payload was: {payload!r})"
    )
    assert payload["model_id"] == model_id
    assert payload["agent_id"] == agent_id


def test_decide_approval_ignores_a_paused_sub_task_sharing_root_run_id(
    client: TestClient, async_session_factory
) -> None:
    """A delegated sub-agent can itself hit a *second* approval gate while
    its own resume is running (e.g. the model re-drafts, or moves on to a
    second gated tool) - agent_loop.py's nested-resume recursion pauses that
    sub-task at `waiting_approval` too, using the exact same `root_run_id`
    as the root task. `decide_approval`'s lookup must not resolve to
    whichever one the query happens to return first: only the parentless
    root task is ever meant to be resumed directly from this route."""
    token, org_id = _register(client, "resume-owner-2@test.com")

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

            root_agent = Agent(org_id=org_id, name="assistant", model_id=model.id, tools=[])
            session.add(root_agent)
            worker_agent = Agent(org_id=org_id, name="email-worker", model_id=model.id, tools=[])
            session.add(worker_agent)
            await session.commit()
            await session.refresh(root_agent)
            await session.refresh(worker_agent)

            chat_session = Session(
                org_id=org_id,
                agent_id=root_agent.id,
                agent_release_id=None,
                title="Original conversation",
            )
            session.add(chat_session)
            await session.commit()
            await session.refresh(chat_session)

            # The delegated sub-task: same root_run_id, but it has a parent
            # and belongs to a *different* agent than the chat session.
            # Inserted (and timestamped) before the root task so that an
            # unfiltered query's natural row order would return it first -
            # a filter-less version of this lookup must be proven to fail
            # here, not accidentally pass because of insertion order.
            sub_task = Task(
                id="sub-task-2",
                org_id=org_id,
                parent_task_id="root-task-2",
                root_run_id="root-task-2",
                agent_id=worker_agent.id,
                depth=1,
                goal="draft the email",
                status="waiting_approval",
                created_at=utc_now(),
            )
            session.add(sub_task)
            await session.commit()

            root_task = Task(
                id="root-task-2",
                org_id=org_id,
                parent_task_id=None,
                root_run_id="root-task-2",
                agent_id=root_agent.id,
                depth=0,
                goal="send the farewell email",
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
                args_snapshot={"draft_id": "d-2"},
                requested_by=None,
                owning_task_id=sub_task.id,
            )
            return approval.id, chat_session.id, root_agent.id, model.id

    import anyio

    approval_id, chat_session_id, root_agent_id, model_id = anyio.run(_seed)
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    with patch("app.api.v1.routes.approvals.run_chat_detached", new=AsyncMock()) as mock_resume:
        decided = client.post(
            f"/api/approvals/{approval_id}/decide",
            headers=headers,
            json={"decision": "approved", "reason": ""},
        )
        assert decided.status_code == 200, decided.text

    assert mock_resume.await_count == 1
    payload = mock_resume.await_args.args[0]
    assert payload["agent_id"] == root_agent_id, (
        "must resume the parentless root task, not the paused sub-task "
        f"sharing its root_run_id (payload was: {payload!r})"
    )
    assert payload["session_id"] == chat_session_id
    assert payload["model_id"] == model_id
    assert payload["run_id"] == "root-task-2"


@pytest.mark.asyncio
async def test_prepare_run_pins_model_override_for_process_resume(async_session_factory) -> None:
    async with async_session_factory() as session:
        from app.models.organization import Organization

        org = Organization(id="org-model-pin", name="Model Pin Org", slug="model-pin-org")
        provider = Provider(
            id="provider-model-pin",
            org_id=org.id,
            name="Provider",
            key="provider",
            base_url="http://provider",
            api_key="key",
        )
        default_model = Model(
            id="model-default-pin",
            org_id=org.id,
            provider_id=provider.id,
            name="default",
            display_name="Default",
        )
        switched_model = Model(
            id="model-switched-pin",
            org_id=org.id,
            provider_id=provider.id,
            name="switched",
            display_name="Switched",
        )
        agent = Agent(
            id="agent-model-pin",
            org_id=org.id,
            name="Pinned Agent",
            model_id=default_model.id,
        )
        session.add_all([org, provider, default_model, switched_model, agent])
        await session.commit()

        from app.schemas.chat import ChatRequest
        from app.services.chat_service import ChatService

        _, _, task = await ChatService(session).prepare_run(
            org.id,
            ChatRequest(
                agent_id=agent.id,
                model_id=switched_model.id,
                message="continue after approval",
                run_id="run-model-pin",
            ),
            "run-model-pin",
            user_id="user-model-pin",
            user_role="org_admin",
        )

        assert task.progress["model_id"] == switched_model.id
