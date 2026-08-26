from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import run_workflow
from app.db.base import Base
from app.models.organization import Organization
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
        output_text, event_logs, run_id = await run_workflow(
            wf,
            input_text="Daily Morning Run Context",
            db=session,
            stream=False,
            force_inline=True,
        )
        assert run_id is not None
        assert output_text is not None
        assert (
            "Daily Morning Run Context" in output_text
            or "Triage routed" in output_text
            or "Google Workspace" in output_text
        )


@pytest.mark.asyncio
async def test_google_drive_scan_automation_dag_execution(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Drive Corp", slug="drive-corp")
        session.add(org)
        await session.flush()

        drive_dag = {
            "nodes": [
                {
                    "id": "trigger_6am",
                    "kind": "scheduler",
                    "label": "Daily 06:00 Trigger",
                    "config": {"cron": "0 6 * * *", "schedule_label": "Daily at 06:00"},
                },
                {
                    "id": "drive_connector",
                    "kind": "integration",
                    "label": "Google Drive Scanner",
                    "config": {"source": "google_drive"},
                },
                {
                    "id": "doc_triager",
                    "kind": "triager",
                    "label": "Filter Recent Documents",
                    "config": {"policy": "filter_recent_docs"},
                },
                {
                    "id": "doc_analyzer",
                    "kind": "agent",
                    "label": "Document Intelligence Agent",
                    "agent_id": None,
                    "config": {},
                },
                {
                    "id": "final_output",
                    "kind": "output",
                    "label": "Drive Scan Digest",
                    "config": {},
                },
            ],
            "edges": [
                {"from_": "trigger_6am", "to": "drive_connector"},
                {"from_": "drive_connector", "to": "doc_triager"},
                {"from_": "doc_triager", "to": "doc_analyzer"},
                {"from_": "doc_analyzer", "to": "final_output"},
            ],
        }

        WorkflowService.validate_graph(drive_dag)

        service = WorkflowService(session)
        wf = await service.create(
            org.id,
            {
                "name": "Daily 06:00 Google Drive Scanner",
                "description": "Scans Google Drive daily at 06:00",
                "graph": drive_dag,
            },
        )
        assert wf.id is not None

        # Execute drive scan workflow (with empty on-demand input, as standard for scheduled triggers)
        output_text, _logs, run_id = await run_workflow(
            wf,
            input_text="",
            db=session,
            stream=False,
            force_inline=True,
        )
        assert run_id is not None
        assert output_text is not None
        assert (
            "Google Drive" in output_text
            or "Document Intelligence Agent" in output_text
            or "Drive Scan Digest" in output_text
        )
