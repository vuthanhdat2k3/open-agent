"""Cross-org agent rejection in workflow validation (Fix #8).

A workflow pointing at an ``agent_id`` from a different org must be rejected
at save time with a clear ``agent_id`` error, not at runtime with an opaque
"agent not found" deep inside the worker. The structural check
(``validate_graph``) stays sync; the new ownership check lives in the
async ``_validate_agent_ownership`` helper.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.workflow import WorkflowValidationError
from app.services.workflow_service import WorkflowService


def _node(kind: str, **kwargs) -> dict:
    base = {"id": f"n-{kind}", "kind": kind, "label": kind, "parameters": {}}
    base["parameters"].update(kwargs)
    return base


@pytest.mark.asyncio
async def test_inherit_agent_in_other_org_is_rejected() -> None:
    """An inherit-mode agent node pointing at an agent owned by a different
    org must raise WorkflowValidationError with field=agent_id."""
    service = WorkflowService.__new__(WorkflowService)  # skip __init__
    service.repo = MagicMock()
    # Repo DB returns None for the agent_id (not in this org).
    service.repo.db = MagicMock()
    service.repo.db.scalar = AsyncMock(return_value=None)

    graph = {
        "nodes": [
            _node("input", input_field="x", required=True),
            _node("agent", mode="inherit", agent_id="foreign-agent-id"),
            _node("output", include="all_inputs"),
        ],
        "edges": [
            {"from_": "n-input", "to": "n-agent"},
            {"from_": "n-agent", "to": "n-output"},
        ],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        await service._validate_agent_ownership(graph, org_id="org-local")
    errors = exc_info.value.errors
    assert any(
        e["node_id"] == "n-agent" and e["field"] == "agent_id" and "not in this organization" in e["message"]
        for e in errors
    ), f"expected cross-org agent error, got: {errors}"


@pytest.mark.asyncio
async def test_inherit_agent_in_same_org_is_accepted() -> None:
    """An inherit-mode agent node pointing at an agent owned by the same
    org must pass without errors."""
    service = WorkflowService.__new__(WorkflowService)
    service.repo = MagicMock()
    service.repo.db = MagicMock()
    service.repo.db.scalar = AsyncMock(return_value="local-agent-id")

    graph = {
        "nodes": [
            _node("input", input_field="x", required=True),
            _node("agent", mode="inherit", agent_id="local-agent-id"),
            _node("output", include="all_inputs"),
        ],
        "edges": [],
    }

    # Must not raise.
    await service._validate_agent_ownership(graph, org_id="org-local")


@pytest.mark.asyncio
async def test_legacy_top_level_agent_id_is_checked() -> None:
    """Pre-rewrite graphs that put ``agent_id`` on the node instead of
    inside ``parameters`` must still be checked for cross-org references.
    """
    service = WorkflowService.__new__(WorkflowService)
    service.repo = MagicMock()
    service.repo.db = MagicMock()
    service.repo.db.scalar = AsyncMock(return_value=None)

    graph = {
        "nodes": [
            _node("input", input_field="x", required=True),
            # No mode + legacy top-level agent_id => inherit path.
            {"id": "n-agent", "kind": "agent", "label": "a", "parameters": {}, "agent_id": "foreign-id"},
            _node("output", include="all_inputs"),
        ],
        "edges": [],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        await service._validate_agent_ownership(graph, org_id="org-local")
    assert any(e["field"] == "agent_id" for e in exc_info.value.errors)


@pytest.mark.asyncio
async def test_catalog_template_skips_ownership_check() -> None:
    """Catalog-template graphs intentionally leave agent binding to runtime
    (the worker resolves to the org's first enabled model) so the
    ownership check must skip them.
    """
    service = WorkflowService.__new__(WorkflowService)
    service.repo = MagicMock()
    service.repo.db = MagicMock()
    # Would raise if called, but the function must not reach the DB.
    service.repo.db.scalar = AsyncMock(side_effect=AssertionError("should not query"))

    graph = {
        "kind": "catalog_template",  # marker set by template_dags
        "nodes": [
            _node("input", input_field="x", required=True),
            _node("agent", mode="inherit", agent_id="placeholder"),
            _node("output", include="all_inputs"),
        ],
        "edges": [],
    }

    # Must not raise; must not query the DB.
    await service._validate_agent_ownership(graph, org_id="org-local")
    assert not service.repo.db.scalar.called


@pytest.mark.asyncio
async def test_custom_mode_agent_skips_ownership_check() -> None:
    """Custom-mode agent nodes have no inherited agent_id, so the
    ownership check is a no-op (nothing to look up)."""
    service = WorkflowService.__new__(WorkflowService)
    service.repo = MagicMock()
    service.repo.db = MagicMock()
    service.repo.db.scalar = AsyncMock(side_effect=AssertionError("should not query"))

    graph = {
        "nodes": [
            _node("input", input_field="x", required=True),
            _node("agent", mode="custom", system_prompt="x", model_id="m"),
            _node("output", include="all_inputs"),
        ],
        "edges": [],
    }

    await service._validate_agent_ownership(graph, org_id="org-local")
    assert not service.repo.db.scalar.called
