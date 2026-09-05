"""M2 regression: the Gmail integration node must persist a durable cursor and
resume incrementally across runs.

Before the fix, `_integration_gmail` always called `list_new(cursor=None)`, so
a scheduled automation re-read the whole mailbox on every run and re-processed
already-seen emails. The durable Gmail checkpoint (`history_id`) is now persisted
in `node_run.output.data["cursor"]` and `_load_prior_gmail_cursor` feeds it back
as the starting point of the next run.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import _load_prior_gmail_cursor
from app.db.base import Base
from app.models.organization import Organization
from app.models.workflow import Workflow
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun


def _factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    return engine


async def _seed_org_and_workflow(session: AsyncSession) -> Workflow:
    org = Organization(name="Cursor Org", slug="cursor-org")
    session.add(org)
    await session.commit()
    workflow = Workflow(org_id=org.id, name="Gmail Delta", graph={"nodes": [], "edges": []})
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)
    return workflow


async def _add_run(session, workflow, status, finished_at) -> WorkflowRun:
    run = WorkflowRun(
        org_id=workflow.org_id,
        workflow_id=workflow.id,
        status=status,
        finished_at=finished_at,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def _add_node_run(session, run_id, node_id, status, data, finished_at) -> WorkflowNodeRun:
    nr = WorkflowNodeRun(
        workflow_run_id=run_id,
        node_id=node_id,
        status=status,
        attempt=1,
        output={"text": "", "data": data},
        finished_at=finished_at,
    )
    session.add(nr)
    await session.commit()
    return nr


async def test_prior_succeeded_run_supplies_the_cursor() -> None:
    engine = _factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        wf = await _seed_org_and_workflow(session)
        now = datetime.utcnow()
        # A successful prior run that persisted the durable Gmail checkpoint.
        prior = await _add_run(session, wf, "succeeded", now - timedelta(minutes=10))
        await _add_node_run(
            session,
            prior.id,
            "mail_node",
            "succeeded",
            {"emails": [], "cursor": "109523"},
            now - timedelta(minutes=9),
        )
        # A failed run of the same node (must be ignored).
        failed = await _add_run(session, wf, "failed", now - timedelta(minutes=5))
        await _add_node_run(
            session,
            failed.id,
            "mail_node",
            "failed",
            {"emails": []},
            now - timedelta(minutes=4),
        )
        # The "current" run executing the node right now.
        current = await _add_run(session, wf, "running", None)
        await _add_node_run(
            session,
            current.id,
            "mail_node",
            "running",
            {},
            None,
        )

        cursor = await _load_prior_gmail_cursor(session, current.id, "mail_node")
        assert cursor == "109523"
    await engine.dispose()


async def test_no_cursor_when_no_prior_success() -> None:
    engine = _factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        wf = await _seed_org_and_workflow(session)
        current = await _add_run(session, wf, "running", None)
        await _add_node_run(session, current.id, "mail_node", "running", {}, None)

        cursor = await _load_prior_gmail_cursor(session, current.id, "mail_node")
        assert cursor is None
    await engine.dispose()


async def test_latest_prior_success_wins() -> None:
    engine = _factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        wf = await _seed_org_and_workflow(session)
        now = datetime.utcnow()
        older = await _add_run(session, wf, "succeeded", now - timedelta(hours=2))
        await _add_node_run(
            session,
            older.id,
            "mail_node",
            "succeeded",
            {"cursor": "1000"},
            now - timedelta(hours=2),
        )
        newer = await _add_run(session, wf, "succeeded", now - timedelta(minutes=1))
        await _add_node_run(
            session,
            newer.id,
            "mail_node",
            "succeeded",
            {"cursor": "2050"},
            now - timedelta(minutes=1),
        )
        current = await _add_run(session, wf, "running", None)

        cursor = await _load_prior_gmail_cursor(session, current.id, "mail_node")
        assert cursor == "2050"
    await engine.dispose()