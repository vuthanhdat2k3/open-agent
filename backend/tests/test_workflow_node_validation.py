"""Tier 1 tests for workflow node validation (Phase 1)."""

from __future__ import annotations

from app.core.workflow.node_definitions import NODE_DEFINITIONS, get_node_definition
from app.schemas.workflow import WorkflowValidationError
from app.services.workflow_service import WorkflowService


def _graph(nodes: list[dict], edges: list[dict] | None = None) -> dict:
    return {"nodes": nodes, "edges": edges or []}


def _err(graph: dict) -> list[dict[str, str]]:
    try:
        WorkflowService.validate_graph(graph)
    except WorkflowValidationError as exc:
        return exc.errors
    return []


def test_definitions_cover_all_kinds() -> None:
    kinds = {"input", "scheduler", "integration", "triager", "agent", "tool", "merge", "approval", "sub_workflow", "output"}
    assert set(NODE_DEFINITIONS) == kinds


def test_every_definition_has_common_fields() -> None:
    for kind, definition in NODE_DEFINITIONS.items():
        names = {f.name for f in definition.fields}
        assert "input_mapping" in names, kind
        assert "onError" in names, kind


def test_definition_has_default_parameters() -> None:
    assert NODE_DEFINITIONS["agent"].default_parameters.get("temperature") == 0.7
    assert NODE_DEFINITIONS["scheduler"].default_parameters["frequency"] == "daily"


def test_valid_input_output_graph() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input", "label": "Input", "parameters": {"input_field": "Run input"}},
            {"id": "out", "kind": "output", "label": "Output", "parameters": {"include": "all_inputs"}},
        ],
        [{"from_": "in", "to": "out"}],
    )
    assert _err(graph) == []


def test_missing_entry_node() -> None:
    graph = _graph([{"id": "out", "kind": "output", "label": "Output"}])
    assert any(e["field"] == "graph" for e in _err(graph))


def test_unknown_kind() -> None:
    graph = _graph(
        [{"id": "in", "kind": "input"}, {"id": "x", "kind": "bogus"}],
        [{"from_": "in", "to": "x"}],
    )
    assert any(e["field"] == "kind" for e in _err(graph))


def test_cycle_detected() -> None:
    graph = _graph(
        [
            {"id": "a", "kind": "input"},
            {"id": "b", "kind": "tool", "parameters": {"tool": "web_search"}},
        ],
        [{"from_": "a", "to": "b"}, {"from_": "b", "to": "a"}],
    )
    assert any("cycle" in e["message"] for e in _err(graph))


def test_custom_agent_requires_model() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input"},
            {"id": "agent", "kind": "agent", "parameters": {"mode": "custom", "system_prompt": "hi"}},
            {"id": "out", "kind": "output"},
        ],
        [{"from_": "in", "to": "agent"}, {"from_": "agent", "to": "out"}],
    )
    assert any(e["field"] == "model_id" for e in _err(graph))


def test_legacy_agent_id_is_inherit() -> None:
    # Backward compatibility: top-level agent_id means inherit mode; no model needed.
    graph = _graph(
        [
            {"id": "in", "kind": "input", "parameters": {"input_field": "Run input"}},
            {"id": "agent", "kind": "agent", "agent_id": "agent-123", "config": {}},
            {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
        ],
        [{"from_": "in", "to": "agent"}, {"from_": "agent", "to": "out"}],
    )
    assert _err(graph) == []


def test_tool_requires_tool_name() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input"},
            {"id": "tool", "kind": "tool", "parameters": {}},
            {"id": "out", "kind": "output"},
        ],
        [{"from_": "in", "to": "tool"}, {"from_": "tool", "to": "out"}],
    )
    assert any(e["field"] == "tool" for e in _err(graph))


def test_input_mapping_unknown_source() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input"},
            {
                "id": "out",
                "kind": "output",
                "parameters": {"input_mapping": [{"field": "x", "source_node_id": "nope"}]},
            },
        ],
        [{"from_": "in", "to": "out"}],
    )
    assert any(e["field"] == "input_mapping" for e in _err(graph))


def test_input_mapping_non_upstream_source() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input"},
            {"id": "other", "kind": "input"},
            {
                "id": "out",
                "kind": "output",
                "parameters": {"input_mapping": [{"field": "x", "source_node_id": "other"}]},
            },
        ],
        [{"from_": "in", "to": "out"}],
    )
    assert any(e["field"] == "input_mapping" for e in _err(graph))


def test_edge_condition_invalid_syntax() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input"},
            {"id": "out", "kind": "output"},
        ],
        [{"from_": "in", "to": "out", "condition": "output ==="}],
    )
    assert any(e["field"] == "condition" for e in _err(graph))


def test_output_selected_requires_selected_from() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input"},
            {"id": "out", "kind": "output", "parameters": {"include": "selected"}},
        ],
        [{"from_": "in", "to": "out"}],
    )
    assert any(e["field"] == "selected_from" for e in _err(graph))


def test_sub_workflow_cannot_self_reference() -> None:
    graph = _graph(
        [
            {"id": "in", "kind": "input"},
            {"id": "sub", "kind": "sub_workflow", "parameters": {"workflow_id": "sub"}},
        ],
        [{"from_": "in", "to": "sub"}],
    )
    assert any(e["field"] == "workflow_id" for e in _err(graph))


def test_get_node_definition() -> None:
    assert get_node_definition("agent") is not None
    assert get_node_definition("bogus") is None
