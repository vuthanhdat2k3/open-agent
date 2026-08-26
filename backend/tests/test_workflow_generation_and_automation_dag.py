from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import run_workflow
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.models.workflow import Workflow
from app.schemas.workflow import GraphNode, WorkflowGraph
from app.services.workflow_service import WorkflowService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_automation_dag_validation_and_engine_execution(async_session_factory) -> None:
    async with async_session_factory() as session:
        # Create an org and sample automation DAG with scheduler, integration, triager, agent, output
        org = Organization(name="DAG Corp", slug="dag-corp")
        session.add(org)
        await session.flush()

        automation_graph = {
            "nodes": [
                {
                    "id": "scheduler_node",
                    "kind": "scheduler",
                    "label": "Morning Trigger",
                    "config": {"cron": "0 7 * * 1-5", "schedule_label": "Weekdays 07:30"},
                },
                {
                    "id": "integration_node",
                    "kind": "integration",
                    "label": "Gmail & Calendar Connector",
                    "config": {"source": "gmail_and_calendar"},
                },
                {
                    "id": "triager_node",
                    "kind": "triager",
                    "label": "Prioritize Tasks",
                    "config": {"policy": "rank_by_urgency"},
                },
                {
                    "id": "output_node",
                    "kind": "output",
                    "label": "Daily Briefing",
                    "config": {},
                },
            ],
            "edges": [
                {"from_": "scheduler_node", "to": "integration_node"},
                {"from_": "integration_node", "to": "triager_node"},
                {"from_": "triager_node", "to": "output_node"},
            ],
        }

        # 1. Validation test
        WorkflowService.validate_graph(automation_graph)

        # 2. Creation test
        service = WorkflowService(session)
        wf = await service.create(
            org.id,
            {
                "name": "Morning Command Center Test",
                "description": "Automated morning test",
                "graph": automation_graph,
            },
        )
        assert wf.id is not None

        # 3. Execution test
        result = await run_workflow(
            wf,
            input_text="Daily Morning Run Context",
            db=session,
            stream=False,
            force_inline=True,
        )
        assert result is not None
        assert "Scheduled trigger" in result or "Integration data" in result or "Triage complete" in result or "Daily Morning Run Context" in result
