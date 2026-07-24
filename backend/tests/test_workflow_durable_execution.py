from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.tools.registry import register
from app.core.tools.types import ToolContext, ToolSpec
from app.core.workflow.engine import run_workflow
from app.db.base import Base
from app.models.organization import Organization
from app.models.workflow import Workflow
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun


async def _seed_workflow(session: AsyncSession, graph: dict[str, Any]) -> Workflow:
    org = Organization(name="Workflow Org", slug="workflow-org")
    session.add(org)
    await session.commit()
    await session.refresh(org)

    workflow = Workflow(org_id=org.id, name="Durable", graph=graph)
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)
    return workflow


async def test_workflow_persists_run_and_node_runs_inline() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        workflow = await _seed_workflow(
            session,
            {
                "nodes": [
                    {"id": "in", "kind": "input"},
                    {"id": "merge", "kind": "merge"},
                    {"id": "out", "kind": "output"},
                ],
                "edges": [
                    {"from_": "in", "to": "merge"},
                    {"from_": "merge", "to": "out"},
                ],
            },
        )

        output, events, workflow_run_id = await run_workflow(
            workflow,
            "hello durable",
            session,
            stream=False,
        )

        assert output == "hello durable"
        assert workflow_run_id
        assert any(ev["event"] == "workflow_start" for ev in events)
        run = (
            await session.execute(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id))
        ).scalar_one()
        assert run.status == "succeeded"
        assert run.output == {"text": "hello durable"}
        node_runs = (
            await session.execute(
                select(WorkflowNodeRun).where(WorkflowNodeRun.workflow_run_id == workflow_run_id)
            )
        ).scalars().all()
        assert [(node.node_id, node.status) for node in node_runs] == [
            ("in", "succeeded"),
            ("merge", "succeeded"),
            ("out", "succeeded"),
        ]

    await engine.dispose()


async def test_workflow_retry_records_each_attempt() -> None:
    attempts = 0

    async def flaky(args: dict[str, Any], ctx: ToolContext) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("not yet")
        return "ok"

    register(
        ToolSpec(
            name="m6_flaky",
            description="fails twice",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            run=flaky,
        )
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        workflow = await _seed_workflow(
            session,
            {
                "nodes": [
                    {"id": "in", "kind": "input"},
                    {
                        "id": "tool",
                        "kind": "tool",
                        "config": {
                            "tool": "m6_flaky",
                            "retry": {"max_attempts": 3, "backoff_s": 0},
                        },
                    },
                    {"id": "out", "kind": "output"},
                ],
                "edges": [
                    {"from_": "in", "to": "tool"},
                    {"from_": "tool", "to": "out"},
                ],
            },
        )

        output, _events, workflow_run_id = await run_workflow(workflow, "start", session)

        assert output == "ok"
        node_runs = (
            await session.execute(
                select(WorkflowNodeRun)
                .where(WorkflowNodeRun.workflow_run_id == workflow_run_id)
                .order_by(WorkflowNodeRun.node_id, WorkflowNodeRun.attempt)
            )
        ).scalars().all()
        tool_runs = [node for node in node_runs if node.node_id == "tool"]
        assert [node.status for node in tool_runs] == ["failed", "failed", "succeeded"]
        assert [node.attempt for node in tool_runs] == [1, 2, 3]

    await engine.dispose()

