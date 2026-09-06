"""The workflow `approval` node's title/instructions/approver_user_ids/
timeout_minutes were declared in the schema but never persisted or enforced
anywhere. Regression coverage for making them real.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.guardrails.approval import request_approval, sweep_expired_approvals
from app.db.base import Base, utc_now
from app.services.workflow_service import strip_unknown_node_parameters


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_request_approval_stores_workflow_node_fields(session_factory):
    async with session_factory() as db:
        approval = await request_approval(
            db,
            org_id="org-1",
            run_type="workflow",
            run_id="run-1",
            node_id="approve-step",
            title="Approve the refund",
            instructions="Refund is for $500, check the invoice before approving.",
            approver_user_ids=["user-a", "user-b"],
            expires_at=utc_now() + timedelta(minutes=30),
        )
        assert approval.title == "Approve the refund"
        assert "invoice" in approval.instructions
        assert approval.approver_user_ids == ["user-a", "user-b"]
        assert approval.expires_at is not None


async def test_sweep_expired_approvals_rejects_only_past_deadline(session_factory):
    async with session_factory() as db:
        expired = await request_approval(
            db, org_id="org-1", run_type="workflow", run_id="run-1",
            node_id="a", expires_at=utc_now() - timedelta(minutes=1),
        )
        not_yet = await request_approval(
            db, org_id="org-1", run_type="workflow", run_id="run-2",
            node_id="b", expires_at=utc_now() + timedelta(minutes=30),
        )
        no_timeout = await request_approval(
            db, org_id="org-1", run_type="workflow", run_id="run-3", node_id="c",
        )

        swept = await sweep_expired_approvals(db)

        assert [a.id for a in swept] == [expired.id]
        await db.refresh(expired)
        await db.refresh(not_yet)
        await db.refresh(no_timeout)
        assert expired.status == "rejected"
        assert expired.reason == "auto-declined: timeout"
        assert not_yet.status == "pending"
        assert no_timeout.status == "pending"


async def test_sweep_expired_approvals_is_idempotent(session_factory):
    async with session_factory() as db:
        await request_approval(
            db, org_id="org-1", run_type="workflow", run_id="run-1",
            node_id="a", expires_at=utc_now() - timedelta(minutes=1),
        )
        first = await sweep_expired_approvals(db)
        second = await sweep_expired_approvals(db)
        assert len(first) == 1
        assert second == []


def test_strip_unknown_node_parameters_removes_hallucinated_fields():
    graph = {
        "nodes": [
            {
                "id": "research",
                "kind": "agent",
                "parameters": {
                    "mode": "inherit",
                    "instructions": "Search for tech news.",
                    "not_a_real_field": "should be dropped",
                },
            },
            {
                "id": "output",
                "kind": "output",
                "parameters": {
                    "include": "all_inputs",
                    "delivery_channel": "openagent_chat",
                    "store_name": "brief",
                },
            },
        ]
    }
    stripped = strip_unknown_node_parameters(graph)

    research_params = graph["nodes"][0]["parameters"]
    output_params = graph["nodes"][1]["parameters"]
    assert "not_a_real_field" not in research_params
    assert research_params["instructions"] == "Search for tech news."
    assert "delivery_channel" not in output_params
    assert "store_name" not in output_params
    assert output_params["include"] == "all_inputs"
    assert {"node_id": "research", "kind": "agent", "keys": ["not_a_real_field"]} in stripped
    assert any(s["node_id"] == "output" for s in stripped)


def test_strip_unknown_node_parameters_leaves_valid_graph_untouched():
    graph = {
        "nodes": [
            {"id": "trigger", "kind": "scheduler", "parameters": {"frequency": "daily", "time": "08:00"}},
        ]
    }
    stripped = strip_unknown_node_parameters(graph)
    assert stripped == []
    assert graph["nodes"][0]["parameters"] == {"frequency": "daily", "time": "08:00"}
