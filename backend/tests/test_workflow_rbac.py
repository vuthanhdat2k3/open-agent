"""Tier 2 tests for RBAC: user workflow authoring (Phase 2)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.authz.policy import Role, has_permission
from app.core.workflow.template_dags import TEMPLATE_DAGS, materialize_template_graph
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


# --- policy matrix ---


def test_user_has_workflow_authoring_permissions() -> None:
    assert has_permission(Role.user, "workflows:create")
    assert has_permission(Role.user, "workflows:update")
    assert has_permission(Role.user, "workflows:delete")
    assert has_permission(Role.user, "workflows:read")
    assert has_permission(Role.user, "workflows:run")


def test_user_still_lacks_admin_scoped_perms() -> None:
    assert not has_permission(Role.user, "workflows:manage")
    assert not has_permission(Role.user, "orgs:manage")


# --- template DAG materialization ---


def test_all_catalog_templates_have_dag_graphs() -> None:
    # Floor, not an exact count: new templates are added to the catalog over
    # time, and a hardcoded equality silently broke (flaky) when the 8th
    # template landed. The real invariant is that EVERY catalog entry is a
    # well-formed DAG template.
    assert len(TEMPLATE_DAGS) >= 7
    for key, graph in TEMPLATE_DAGS.items():
        assert graph.get("kind") == "catalog_template", key
        assert "nodes" in graph and graph["nodes"], key
        assert "edges" in graph, key


def test_template_dags_pass_validation() -> None:
    for _key, graph in TEMPLATE_DAGS.items():
        # The template DAG must satisfy the (backward-compatible) validator.
        WorkflowService.validate_graph(graph)


def test_materialized_graph_binds_installation_runtime_settings() -> None:
    graph = materialize_template_graph(
        "weekly-account-review",
        timezone="Asia/Ho_Chi_Minh",
        schedule={"kind": "daily", "time": "07:30"},
        settings={
            "connection_id": "gmail-1",
            "calendar_connection_id": "calendar-1",
        },
        default_agent_id="agent-1",
    )
    scheduler = next(node for node in graph["nodes"] if node["kind"] == "scheduler")
    integration = next(node for node in graph["nodes"] if node["kind"] == "integration")
    agent = next(node for node in graph["nodes"] if node["kind"] == "agent")
    assert scheduler["parameters"] == {
        "frequency": "daily",
        "time": "07:30",
        "timezone": "Asia/Ho_Chi_Minh",
        "enabled": True,
    }
    assert integration["parameters"]["connection_id"] == "gmail-1"
    assert integration["parameters"]["calendar_connection_id"] == "calendar-1"
    assert agent["parameters"]["mode"] == "inherit"
    assert agent["parameters"]["agent_id"] == "agent-1"


def test_event_materialization_marks_event_trigger() -> None:
    graph = materialize_template_graph(
        "new-customer-intelligence",
        timezone="Asia/Ho_Chi_Minh",
        schedule={"kind": "event"},
        settings={"connection_id": "gmail-1"},
    )
    assert not any(node["kind"] == "scheduler" for node in graph["nodes"])
    input_node = next(node for node in graph["nodes"] if node["kind"] == "input")
    integration = next(node for node in graph["nodes"] if node["kind"] == "integration")
    assert input_node["parameters"]["trigger_type"] == "event"
    assert integration["parameters"]["connection_id"] == "gmail-1"


# --- ownership scoping through the service ---


@pytest.mark.asyncio
async def test_create_sets_created_by_user(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="RBAC Corp", slug="rbac-corp")
        session.add(org)
        await session.flush()
        service = WorkflowService(session)
        wf = await service.create(
            org.id,
            {
                "name": "My Workflow",
                "description": "",
                "graph": {
                    "nodes": [
                        {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
                        {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
                    ],
                    "edges": [{"from_": "in", "to": "out"}],
                },
            },
            user_id="user-1",
        )
        assert wf.created_by_user_id == "user-1"


@pytest.mark.asyncio
async def test_install_graph_is_editable_workflow(async_session_factory) -> None:
    async with async_session_factory() as session:
        org = Organization(name="Install Corp", slug="install-corp")
        session.add(org)
        await session.flush()
        graph = TEMPLATE_DAGS["follow-up-radar"]
        service = WorkflowService(session)
        wf = await service.create(
            org.id,
            {"name": "Follow-up Radar", "description": "", "graph": graph},
            user_id="user-1",
        )
        # The materialized workflow holds the real DAG (not a placeholder).
        assert wf.graph.get("kind") == "catalog_template"
        assert len(wf.graph.get("nodes", [])) >= 5
        # And it can be updated by its owner via the service once the user
        # provides a model for the custom agent (editor fills this in).
        updated_graph = {
            "nodes": [
                {
                    **n,
                    "parameters": (
                        {**n.get("parameters", {}), "model_id": "model-1"}
                        if n.get("kind") == "agent"
                        else n.get("parameters", {})
                    ),
                }
                for n in wf.graph["nodes"]
            ],
            "edges": wf.graph["edges"],
        }
        updated = await service.update(
            org.id,
            wf.id,
            {"graph": updated_graph},
        )
        assert updated.id == wf.id
