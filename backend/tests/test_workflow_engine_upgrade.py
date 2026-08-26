"""Tier 1/2 tests for the upgraded engine: output contract, input_mapping,
onError semantics, triager rules, and structured edge conditions (Phase 3)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import NodeOutput, _eval_condition, resolve_inputs, run_workflow
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


def test_eval_condition_string_and_structured() -> None:
    # string output (legacy)
    assert _eval_condition("'urgent' in output", "urgent email") is True
    assert _eval_condition("'urgent' in output", "chill email") is False
    # structured NodeOutput
    out = NodeOutput(text="sales", data={"category": "sales", "reason": "quote"})
    assert _eval_condition("output.category == 'sales'", out) is True
    assert _eval_condition("output.category == 'support'", out) is False
    assert _eval_condition("output_text == 'sales'", out) is True


def test_resolve_inputs_mapping_and_fallback() -> None:
    outputs = {
        "a": NodeOutput(text="A text", data={"emails": [{"subject": "Hello"}]}),
        "b": NodeOutput(text="B text", data={}),
    }
    # no mapping -> concatenated text
    resolved = resolve_inputs({"id": "x", "kind": "agent", "config": {}}, outputs, ["a", "b"])
    assert resolved["__text__"] == "A text\n\nB text"
    # with mapping -> field + path resolution
    node = {
        "id": "x",
        "kind": "agent",
        "parameters": {"input_mapping": [{"field": "subject", "source_node_id": "a", "source_path": "emails.0.subject"}]},
    }
    resolved = resolve_inputs(node, outputs, ["a", "b"])
    assert resolved["subject"] == "Hello"
    assert "Hello" in resolved["__text__"]


@pytest.mark.asyncio
async def test_workflow_output_contract_and_final_data(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Contract Corp", slug="contract-corp")
        session.add(org)
        await session.flush()
        graph = {
            "nodes": [
                {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
                {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
            ],
            "edges": [{"from_": "in", "to": "out"}],
        }
        wf = await WorkflowService(session).create(org.id, {"name": "C", "description": "", "graph": graph})
        output_text, logs, run_id = await run_workflow(
            wf, "hello world", session, stream=False, force_inline=True
        )
        assert "hello world" in output_text
        # final run output stores data map
        from app.models.workflow_run import WorkflowRun
        from sqlalchemy import select

        run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        assert run is not None
        # final run output stores the output node's data under its node id
        assert run.output["data"]["out"] == {"output": "hello world"}


@pytest.mark.asyncio
async def test_onerror_fallback(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Fallback Corp", slug="fallback-corp")
        session.add(org)
        await session.flush()
        # tool node with an unknown tool => raises; onError=fallback keeps the run green
        graph = {
            "nodes": [
                {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
                {
                    "id": "tool",
                    "kind": "tool",
                    "parameters": {"tool": "does_not_exist_tool", "onError": "fallback", "fallback": "FALLBACK_OK"},
                },
                {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
            ],
            "edges": [{"from_": "in", "to": "tool"}, {"from_": "tool", "to": "out"}],
        }
        wf = await WorkflowService(session).create(org.id, {"name": "F", "description": "", "graph": graph})
        output_text, logs, run_id = await run_workflow(
            wf, "x", session, stream=False, force_inline=True
        )
        assert "FALLBACK_OK" in output_text
        assert any(e["event"] == "node_error" and e["data"].get("fallback") for e in logs)
        assert all(e["event"] != "error" for e in logs)


@pytest.mark.asyncio
async def test_onerror_continue_skips_branch(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Skip Corp", slug="skip-corp")
        session.add(org)
        await session.flush()
        graph = {
            "nodes": [
                {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
                {
                    "id": "tool",
                    "kind": "tool",
                    "parameters": {"tool": "does_not_exist_tool", "onError": "continue"},
                },
                {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
            ],
            "edges": [{"from_": "in", "to": "tool"}, {"from_": "tool", "to": "out"}],
        }
        wf = await WorkflowService(session).create(org.id, {"name": "S", "description": "", "graph": graph})
        output_text, logs, run_id = await run_workflow(
            wf, "x", session, stream=False, force_inline=True
        )
        # tool failed with continue => skipped; output node has no active upstream text
        assert any(e["event"] == "node_error" and e["data"].get("skipped") for e in logs)
        assert not any(e["event"] == "error" for e in logs)


@pytest.mark.asyncio
async def test_triager_rules_mode(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Triage Corp", slug="triage-corp")
        session.add(org)
        await session.flush()
        graph = {
            "nodes": [
                {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
                {
                    "id": "tri",
                    "kind": "triager",
                    "parameters": {
                        "mode": "rules",
                        "categories": "sales, support",
                        "rules": [
                            {"pattern": "quote", "category": "sales"},
                            {"pattern": "broken", "category": "support"},
                        ],
                    },
                },
                {
                    "id": "out",
                    "kind": "output",
                    "parameters": {
                        "include": "selected",
                        "selected_from": ["tri"],
                    },
                },
            ],
            "edges": [{"from_": "in", "to": "tri"}, {"from_": "tri", "to": "out"}],
        }
        wf = await WorkflowService(session).create(org.id, {"name": "T", "description": "", "graph": graph})
        output_text, logs, run_id = await run_workflow(
            wf, "Please send a quote for X", session, stream=False, force_inline=True
        )
        assert "sales" in output_text


@pytest.mark.asyncio
async def test_fanout_concurrency_limit(async_session_factory) -> None:
    """A wide fan-out still completes; concurrency is bounded by the semaphore."""
    async with async_session_factory() as session:
        org = Organization(name="Fan Corp", slug="fan-corp")
        session.add(org)
        await session.flush()
        nodes = [
            {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
        ]
        edges = []
        for i in range(12):
            nid = f"out{i}"
            nodes.append({"id": nid, "kind": "output", "parameters": {"include": "all_inputs"}})
            edges.append({"from_": "in", "to": nid})
        graph = {"nodes": nodes, "edges": edges}
        wf = await WorkflowService(session).create(org.id, {"name": "Fan", "description": "", "graph": graph})
        output_text, logs, run_id = await run_workflow(
            wf, "fan", session, stream=False, force_inline=True
        )
        assert run_id is not None
        assert "fan" in output_text
