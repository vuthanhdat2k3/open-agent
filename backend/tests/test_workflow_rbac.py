"""Tier 2 tests for RBAC: user workflow authoring (Phase 2)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.authz.policy import Role, has_permission
from app.core.workflow.template_dags import TEMPLATE_DAGS
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
    assert len(TEMPLATE_DAGS) == 7
    for key, graph in TEMPLATE_DAGS.items():
        assert graph.get("kind") == "catalog_template", key
        assert "nodes" in graph and graph["nodes"], key
        assert "edges" in graph, key


def test_template_dags_pass_validation() -> None:
    for _key, graph in TEMPLATE_DAGS.items():
        # The template DAG must satisfy the (backward-compatible) validator.
        WorkflowService.validate_graph(graph)


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
