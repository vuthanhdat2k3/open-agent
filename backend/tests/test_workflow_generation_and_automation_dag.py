from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import run_workflow
from app.db.base import Base
from app.models.customer_intelligence import CalendarConnection, DriveConnection, EmailConnection
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


@pytest.fixture(autouse=True)
def _stub_ci_credentials(monkeypatch: pytest.MonkeyPatch):
    """Integration node fetches real provider data via CI stack; stub the
    credential refresh so tests don't touch OAuth, and the conftest
    ``ci_mcp_stub`` provides fake provider responses."""

    async def _load_fresh(db, conn):
        return {
            "access_token": "stub-access",
            "refresh_token": "stub-refresh",
            "expires_at": None,
            "token_type": "Bearer",
        }

    monkeypatch.setattr(
        "app.customer_intelligence.oauth.load_fresh_credentials", _load_fresh
    )

    # Calendar provider calls via research module; extend the conftest stub
    # (which only handles email tools) with calendar/event responses.
    async def _research_call(tool: str, args: dict):
        if tool == "calendar_list_events":
            return [
                {
                    "provider_event_id": "evt-1",
                    "title": "Client Advisory Board",
                    "start_at": "2026-08-27T10:00:00+00:00",
                    "end_at": "2026-08-27T11:00:00+00:00",
                    "attendees": ["client@example.com"],
                }
            ]
        raise AssertionError(f"unexpected research MCP tool: {tool}")

    monkeypatch.setattr(
        "app.customer_intelligence.providers.research.call_customer_intelligence_mcp",
        _research_call,
    )

    # Drive provider (not covered by conftest stub) returns one fake file.
    async def _drive_call(tool: str, args: dict):
        if tool == "drive_list_files":
            return [
                {"id": "file-1", "name": "Q3 Report.pdf", "mimeType": "application/pdf", "modifiedTime": "2026-08-25T09:00:00+00:00"}
            ]
        raise AssertionError(f"unexpected drive MCP tool: {tool}")

    monkeypatch.setattr(
        "app.customer_intelligence.providers.drive.call_customer_intelligence_mcp",
        _drive_call,
    )


@pytest.mark.asyncio
async def test_automation_dag_validation_and_engine_execution(async_session_factory) -> None:
    async with async_session_factory() as session:
        # Create an org and sample automation DAG with scheduler, integration, triager, agent, output
        org = Organization(name="DAG Corp", slug="dag-corp")
        session.add(org)
        await session.flush()

        # Connected Gmail + Calendar accounts (integration node fetches real data)
        session.add(EmailConnection(org_id=org.id, created_by_user_id="user-1", provider="gmail", account_email="a@b.c", status="connected", credentials_enc="enc"))
        session.add(CalendarConnection(org_id=org.id, created_by_user_id="user-1", provider="google", account_email="cal@b.c", status="connected", credentials_enc="enc"))
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
            user_id="user-1",
        )
        assert run_id is not None
        assert output_text is not None
        import sys
        for e in event_logs:
            if e["event"] in ("node_error", "error", "done"):
                print(f"\n[{e['event']}] {e['data']}", file=sys.stderr)
        assert (
            "Daily Morning Run Context" in output_text
            or "Triage routed" in output_text
            or "Gmail" in output_text
            or "No email" in output_text
        )


@pytest.mark.asyncio
async def test_google_drive_scan_automation_dag_execution(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Drive Corp", slug="drive-corp")
        session.add(org)
        await session.flush()
        session.add(
            DriveConnection(
                org_id=org.id, created_by_user_id="user-1", account_email="drive@b.c",
                status="connected", credentials_enc="enc",
            )
        )
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
            user_id="user-1",
        )
        assert run_id is not None
        assert output_text is not None
        assert (
            "Google Drive" in output_text
            or "Document Intelligence Agent" in output_text
            or "Drive Scan Digest" in output_text
            or "No files" in output_text
        )
