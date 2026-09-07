from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import create_workflow_run
from app.core.workflow.jobs import run_workflow_detached
from app.db.base import Base
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun


async def _seed(session: AsyncSession, graph: dict[str, Any]) -> tuple[Workflow, User]:
    org = Organization(name="Workflow Org", slug="workflow-org")
    session.add(org)
    await session.commit()
    await session.refresh(org)

    user = User(email="runner@test.com", hashed_password="pw", is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    workflow = Workflow(org_id=org.id, name="Daily Brief", graph=graph)
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)
    return workflow, user


async def test_successful_run_notifies_triggering_user(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        workflow, user = await _seed(
            session,
            {
                "nodes": [
                    {"id": "in", "kind": "input"},
                    {"id": "out", "kind": "output"},
                ],
                "edges": [{"from_": "in", "to": "out"}],
            },
        )
        run = await create_workflow_run(
            workflow, "hello", session, None, user.id, None, None, None, "manual"
        )
        run_id = run.id

    monkeypatch.setattr("app.core.workflow.jobs.SessionLocal", session_factory)
    await run_workflow_detached(run_id)

    async with session_factory() as session:
        run = await session.get(WorkflowRun, run_id)
        assert run.status == "succeeded"

        notifications = (
            await session.execute(
                select(Notification).where(Notification.user_id == user.id)
            )
        ).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].source_type == "workflow_run"
        assert notifications[0].source_id == run_id
        assert "Daily Brief" in notifications[0].title
        assert notifications[0].read_at is None

    await engine.dispose()


async def test_failed_run_notifies_with_error(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # A "tool" node with no registered tool name fails deterministically,
        # without needing any LLM/provider call.
        workflow, user = await _seed(
            session,
            {
                "nodes": [
                    {"id": "in", "kind": "input"},
                    {"id": "broken", "kind": "tool", "parameters": {"tool_name": "does_not_exist"}},
                    {"id": "out", "kind": "output"},
                ],
                "edges": [
                    {"from_": "in", "to": "broken"},
                    {"from_": "broken", "to": "out"},
                ],
            },
        )
        run = await create_workflow_run(
            workflow, "hello", session, None, user.id, None, None, None, "manual"
        )
        run_id = run.id

    monkeypatch.setattr("app.core.workflow.jobs.SessionLocal", session_factory)
    await run_workflow_detached(run_id)

    async with session_factory() as session:
        run = await session.get(WorkflowRun, run_id)
        assert run.status == "failed"

        notifications = (
            await session.execute(
                select(Notification).where(Notification.user_id == user.id)
            )
        ).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].source_type == "workflow_run"
        assert "failed" in notifications[0].title

    await engine.dispose()
