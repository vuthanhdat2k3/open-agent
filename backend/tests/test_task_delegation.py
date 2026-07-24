from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.tools.builtins import _call_agent
from app.core.tools.types import ToolContext
from app.db.base import Base, utc_now
from app.models.agent import Agent
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.task import Task


async def _seed_agent(session: AsyncSession) -> tuple[Organization, Agent, Task]:
    org = Organization(name="Task Org", slug="task-org")
    session.add(org)
    await session.commit()
    await session.refresh(org)

    provider = Provider(org_id=org.id, key="test", name="Test", base_url="http://test")
    session.add(provider)
    await session.commit()
    await session.refresh(provider)

    model = Model(
        org_id=org.id,
        provider_id=provider.id,
        name="test-model",
        display_name="Test Model",
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)

    agent = Agent(
        org_id=org.id,
        name="Worker",
        model_id=model.id,
        system_prompt="work",
        tools=[],
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)

    root = Task(
        org_id=org.id,
        root_run_id="root-run",
        agent_id=agent.id,
        goal="root",
        status="running",
        depth=0,
        started_at=utc_now(),
    )
    session.add(root)
    await session.commit()
    await session.refresh(root)
    return org, agent, root


async def test_call_agent_records_succeeded_child_task(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        org, agent, root = await _seed_agent(session)

        async def fake_run_agent_loop(*args, **kwargs):
            assert kwargs["current_task_id"] != root.id
            assert kwargs["root_run_id"] == "root-run"
            return SimpleNamespace(content="done", usage={"input_tokens": 1}, latency_ms=1)

        monkeypatch.setattr("app.core.agent_loop.run_agent_loop", fake_run_agent_loop)

        result = await _call_agent(
            {"target_agent_id": agent.id, "instruction": "do child work"},
            ToolContext(
                db=session,
                depth=0,
                org_id=org.id,
                current_task_id=root.id,
                root_run_id="root-run",
            ),
        )

        assert result == "done"
        rows = (await session.execute(select(Task).order_by(Task.depth))).scalars().all()
        assert len(rows) == 2
        child = rows[1]
        assert child.parent_task_id == root.id
        assert child.root_run_id == "root-run"
        assert child.agent_id == agent.id
        assert child.goal == "do child work"
        assert child.status == "succeeded"
        assert child.result == "done"
        assert child.token_usage == {"input_tokens": 1}

    await engine.dispose()


async def test_call_agent_records_failed_child_task(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        org, agent, root = await _seed_agent(session)

        async def fake_run_agent_loop(*args, **kwargs):
            raise RuntimeError("subagent exploded")

        monkeypatch.setattr("app.core.agent_loop.run_agent_loop", fake_run_agent_loop)

        result = await _call_agent(
            {"target_agent_id": agent.id, "instruction": "fail"},
            ToolContext(
                db=session,
                depth=0,
                org_id=org.id,
                current_task_id=root.id,
                root_run_id="root-run",
            ),
        )

        assert result == "error: subagent failed: subagent exploded"
        child = (
            await session.execute(select(Task).where(Task.parent_task_id == root.id))
        ).scalar_one()
        assert child.status == "failed"
        assert child.result == "subagent exploded"
        assert child.finished_at is not None

    await engine.dispose()

