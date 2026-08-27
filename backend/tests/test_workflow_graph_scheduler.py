from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base, utc_now
from app.models.organization import Organization
from app.models.outbox import OutboxEvent
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.models.workflow_trigger_state import WorkflowTriggerState
from app.workflows.scheduler import next_run_at, reconcile_trigger_states, run_due_workflows


@pytest.mark.asyncio
async def test_graph_scheduler_materializes_trigger_and_queues_run() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        org = Organization(name="Graph Scheduler", slug="graph-scheduler")
        db.add(org)
        await db.flush()
        workflow = Workflow(
            org_id=org.id,
            name="Scheduled graph",
            graph={
                "nodes": [
                    {
                        "id": "clock",
                        "kind": "scheduler",
                        "parameters": {
                            "frequency": "custom",
                            "custom_cron": "* * * * *",
                            "timezone": "UTC",
                        },
                    },
                    {"id": "output", "kind": "output"},
                ],
                "edges": [{"from_": "clock", "to": "output"}],
            },
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        await reconcile_trigger_states(db, now=utc_now())
        state = await db.scalar(select(WorkflowTriggerState).where(WorkflowTriggerState.workflow_id == workflow.id))
        assert state is not None
        state.next_run_at = utc_now() - timedelta(minutes=1)
        await db.commit()

        result = await run_due_workflows(db, now=utc_now())
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.workflow_id == workflow.id))
        event = await db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_type == "workflow_trigger"))

        assert result == {"due": 1, "queued": 1}
        assert run is not None
        assert run.trigger_node_id == "clock"
        assert run.trigger_type == "scheduler"
        assert run.graph_snapshot == workflow.graph
        assert event is not None

    await engine.dispose()


def test_custom_cron_uses_next_matching_minute() -> None:
    assert next_run_at(
        {"kind": "custom", "cron": "*/15 * * * *"},
        "UTC",
        now=datetime(2026, 8, 27, 10, 7),
    ) == datetime(2026, 8, 27, 10, 15)


def test_custom_cron_uses_standard_monday_to_friday_numbers() -> None:
    # 1-5 means Monday-Friday in standard five-field cron syntax.
    assert next_run_at(
        {"kind": "custom", "cron": "0 7 * * 1-5"},
        "UTC",
        now=datetime(2026, 8, 28, 8, 0),  # Friday after the scheduled time
    ) == datetime(2026, 8, 31, 7, 0)
