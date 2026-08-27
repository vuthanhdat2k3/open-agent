from __future__ import annotations

import json
import re

from simpleeval import simple_eval
from sqlalchemy import select

from app.config import get_settings
from app.core.observability.llm_trace import ObservabilityContext, build_trace_context
from app.core.providers.factory import build_driver
from app.core.workflow.node_definitions import get_node_definition
from app.db.base import gen_id
from app.models.model import Model
from app.models.provider import Provider
from app.models.workflow import Workflow
from app.repositories.agent_repo import AgentRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.schemas.workflow import WorkflowValidationError

_GENERATE_SYSTEM_PROMPT = """You design workflow graphs for a multi-agent automation platform.

A workflow graph is JSON: {{"name": str, "description": str, "graph": {{"nodes": [...], "edges": [...]}}}}.

Node shape: {{"id": str, "kind": "input"|"agent"|"tool"|"merge"|"output"|"approval"|"scheduler"|"triager"|"integration"|"sub_workflow", "label": str, "agent_id": str|null, "merge_mode": "all"|"any", "parameters": dict}}
- Exactly one entry trigger node:
  * "input" for on-demand interactive requests (parameters: {{"input_field": str}}).
  * "scheduler" for recurring/scheduled automations (parameters: {{"frequency": "daily"|"weekdays"|"weekly"|"hourly"|"custom", "time": "HH:MM", "days_of_week": ["mon"...], "custom_cron": "0 6 * * *"}}).
- At least one "output" node for returning results (parameters: {{"include": "all_inputs"}}).
- "agent" nodes: if matching agents exist below, use their id with mode "inherit". Otherwise set parameters {{"mode": "custom", "system_prompt": str, "model_id": null}} (the system will bind a model).
- "integration" nodes: connect to real data — parameters: {{"source": "google_drive"|"gmail"|"google_calendar"|"webhook", "operation": "list_new"|"search"|"list_events"|"list_files", "max_results": 20}}.
- "triager" nodes: route/classify — parameters: {{"mode": "llm", "categories": "sales, support, spam"}} or {{"mode": "rules", "rules": [{{"pattern": str, "category": str}}]}}.
- "tool" nodes: invoke a registered tool — parameters: {{"tool": str, "arguments": dict}}.
- "approval" nodes: pause for human sign-off — parameters: {{"title": str, "instructions": str}}.
- "sub_workflow" nodes: run another workflow — parameters: {{"workflow_id": str}}.
- "merge" nodes: join parallel branches (merge_mode "all"|"any").

Use "parameters" (NOT "config") for node configuration.

Edge shape: {{"from_": node_id, "to": node_id, "condition": str|null}}.

Examples:
1. "quét driver 6h sáng hàng ngày" (Scan Google Drive daily at 6am):
{{"name": "Daily 06:00 Google Drive Scanner", "description": "Scans Google Drive daily at 06:00, classifies updated documents, and synthesizes a digest.", "graph": {{"nodes": [{{"id": "trigger", "kind": "scheduler", "label": "Daily 06:00 Trigger", "parameters": {{"frequency": "daily", "time": "06:00"}}}}, {{"id": "fetch_drive", "kind": "integration", "label": "Fetch Google Drive Documents", "parameters": {{"source": "google_drive", "operation": "list_files"}}}}, {{"id": "triage", "kind": "triager", "label": "Filter New & Modified Files", "parameters": {{"mode": "llm", "categories": "updated, unchanged"}}}}, {{"id": "analyzer", "kind": "agent", "label": "Document Intelligence Agent", "parameters": {{"mode": "custom", "system_prompt": "Summarize the documents."}}}}, {{"id": "output", "kind": "output", "label": "Drive Scan Digest", "parameters": {{"include": "all_inputs"}}}}], "edges": [{{"from_": "trigger", "to": "fetch_drive"}}, {{"from_": "fetch_drive", "to": "triage"}}, {{"from_": "triage", "to": "analyzer"}}, {{"from_": "analyzer", "to": "output"}}]}}}}

Available agents in this organization:
{agents}

Respond with ONLY the JSON object, no markdown fences, no commentary.
"""


class WorkflowService:
    def __init__(self, db):
        self.repo = WorkflowRepository(db)

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Workflow:
        self.validate_graph(data.get("graph", {}))
        await self._validate_agent_ownership(data.get("graph", {}), org_id=org_id)
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        return await self.repo.create(Workflow(**data))

    async def update(self, org_id: str, id: str, data: dict) -> Workflow:
        wf = await self.repo.get(org_id, id)
        if wf is None:
            raise ValueError("workflow not found")
        if "graph" in data:
            self.validate_graph(data["graph"])
            await self._validate_agent_ownership(data["graph"], org_id=org_id)
        return await self.repo.update(wf, data)

    async def delete(self, org_id: str, id: str) -> bool:
        return await self.repo.delete(org_id, id)

    async def list(self, org_id: str) -> list[Workflow]:
        return await self.repo.list(org_id)

    async def get(self, org_id: str, id: str) -> Workflow | None:
        return await self.repo.get(org_id, id)

    async def generate_graph(self, org_id: str, prompt: str, model_id: str) -> dict:
        agents = await AgentRepository(self.repo.db).list(org_id)
        agents_desc = (
            "\n".join(
                f'- id="{a.id}" name="{a.name}" kind={a.kind}: {a.description or "(no description)"}'
                for a in agents
            )
            if agents
            else "(No custom agents configured yet; default agent will be utilized)"
        )

        res = await self.repo.db.execute(
            select(Model).where(Model.id == model_id, Model.org_id == org_id)
        )
        model = res.scalar_one_or_none()
        if model is None:
            raise ValueError(f"model {model_id} not found")
        res = await self.repo.db.execute(select(Provider).where(Provider.id == model.provider_id))
        provider = res.scalar_one_or_none()
        if provider is None:
            raise ValueError("provider not found for model")

        observability = (
            ObservabilityContext(
                build_trace_context(
                    trace_id=f"workflow-graph-{gen_id()}",
                    session_id=None,
                    org_id=org_id,
                    metadata={"run_type": "workflow_graph_generation"},
                )
            )
            if get_settings().observability_enabled
            else None
        )
        llm = build_driver(
            provider,
            model,
            observability=observability,
            generation_name="workflow-graph-generation",
        )
        messages = [
            {"role": "system", "content": _GENERATE_SYSTEM_PROMPT.format(agents=agents_desc)},
            {"role": "user", "content": prompt},
        ]
        content, _usage, _tool_calls = await llm.complete(messages, temperature=0.3)

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError(f"model did not return valid JSON: {content[:200]}")
        try:
            result = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"model returned malformed JSON: {e}") from e

        graph = result.get("graph")
        if not isinstance(graph, dict):
            raise ValueError("generated response missing 'graph'")
        self.validate_graph(graph)
        await self._validate_agent_ownership(graph, org_id=org_id)

        valid_agent_ids = {a.id for a in agents}
        first_agent_id = agents[0].id if agents else None

        for node in graph.get("nodes", []):
            if node.get("kind") == "agent":
                parameters = node.get("parameters") or {}
                if (
                    parameters.get("mode") == "custom"
                    and not parameters.get("model_id")
                    and first_agent_id
                ):
                    # The system binds the org's default model for custom agents.
                    res = await self.repo.db.execute(
                        select(Model)
                        .where(Model.org_id == org_id, Model.enabled.is_(True))
                        .order_by(Model.created_at.asc())
                        .limit(1)
                    )
                    model = res.scalar_one_or_none()
                    if model is not None:
                        parameters["model_id"] = model.id
            if node.get("merge_mode") is None:
                node.pop("merge_mode", None)
            if node.get("parameters") is None:
                node.pop("parameters", None)
            if node.get("config") is None:
                node.pop("config", None)

        return {
            "name": result.get("name") or "Generated workflow",
            "description": result.get("description") or "",
            "graph": graph,
        }

    @staticmethod
    def validate_graph(graph: dict) -> None:
        errors: list[dict[str, str]] = []
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        ids = {n.get("id") for n in nodes}

        # --- structural ---
        entry_kinds = {"input", "scheduler", "integration"}
        if not any(n.get("kind") in entry_kinds for n in nodes):
            errors.append(
                {
                    "node_id": "",
                    "field": "graph",
                    "message": "graph must have at least one entry trigger node (input, scheduler, or integration)",
                }
            )
        if not any(n.get("kind") in ("agent", "output") for n in nodes):
            errors.append(
                {
                    "node_id": "",
                    "field": "graph",
                    "message": "graph needs at least one agent or output node",
                }
            )
        for e in edges:
            if e.get("from_") not in ids or e.get("to") not in ids:
                errors.append(
                    {
                        "node_id": "",
                        "field": "edge",
                        "message": f"edge references unknown node: {e}",
                    }
                )
            cond = e.get("condition")
            if cond:
                try:
                    simple_eval(
                        cond,
                        names={"output": "", "output_text": "", "output_data": {}},
                        functions={},
                    )
                except Exception:  # noqa: BLE001
                    errors.append(
                        {
                            "node_id": e.get("from_", ""),
                            "field": "condition",
                            "message": f"edge condition is not valid: {cond!r}",
                        }
                    )

        # --- cycle detection (DFS) ---
        adj = {n["id"]: [] for n in nodes}
        for e in edges:
            adj.setdefault(e["from_"], []).append(e["to"])
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n["id"]: WHITE for n in nodes}
        has_cycle = False

        def dfs(u: str) -> bool:
            nonlocal has_cycle
            color[u] = GRAY
            for v in adj[u]:
                if color[v] == GRAY:
                    has_cycle = True
                    return True
                if color[v] == WHITE and dfs(v):
                    return True
            color[u] = BLACK
            return False

        for n in nodes:
            if color[n["id"]] == WHITE and dfs(n["id"]):
                break
        if has_cycle:
            errors.append({"node_id": "", "field": "graph", "message": "graph contains a cycle"})

        # --- per-node parameters validation ---
        upstream: dict[str, set[str]] = {n["id"]: set() for n in nodes}
        for e in edges:
            upstream.setdefault(e["to"], set()).add(e["from_"])

        # transitive upstream closure (for input_mapping reachability)
        reachable: dict[str, set[str]] = {nid: set(anc) for nid, anc in upstream.items()}
        changed = True
        while changed:
            changed = False
            for _nid, anc in reachable.items():
                for a in list(anc):
                    for ga in reachable.get(a, set()):
                        if ga not in anc:
                            anc.add(ga)
                            changed = True

        for n in nodes:
            nid = n.get("id")
            kind = n.get("kind")
            if not nid or not kind:
                errors.append(
                    {"node_id": str(nid), "field": "kind", "message": "node missing id or kind"}
                )
                continue
            definition = get_node_definition(kind)
            if definition is None:
                errors.append(
                    {"node_id": nid, "field": "kind", "message": f"unknown node kind: {kind}"}
                )
                continue
            field_defaults = {f.name: f.default for f in definition.fields if f.default is not None}
            parameters = {
                **field_defaults,
                **(definition.default_parameters or {}),
                **dict(n.get("parameters") or n.get("config") or {}),
            }
            if n.get("agent_id"):
                parameters.setdefault("agent_id", n.get("agent_id"))

            for field in definition.fields:
                if not field.required:
                    continue
                if not _field_visible(field, parameters):
                    continue
                # scheduler legacy compat: a raw `cron`/`custom_cron` in config
                # satisfies the schedule requirement without `frequency`.
                if (
                    kind == "scheduler"
                    and field.name == "frequency"
                    and (parameters.get("cron") or parameters.get("custom_cron"))
                ):
                    continue
                # If this is an agent node and an agent_id is provided, system_prompt and model_id
                # are optional overrides (the base agent supplies them).
                if (
                    kind == "agent"
                    and parameters.get("agent_id")
                    and field.name in ("system_prompt", "model_id")
                ):
                    continue
                # Catalog-template input nodes are event/trigger placeholders
                # (e.g. {"event": "inbound_email"}) — no run-input form field.
                if (
                    kind == "input"
                    and field.name == "input_field"
                    and graph.get("kind") == "catalog_template"
                ):
                    continue
                # Catalog-template agents leave model binding to runtime.
                if (
                    kind == "agent"
                    and field.name == "model_id"
                    and graph.get("kind") == "catalog_template"
                ):
                    continue
                value = parameters.get(field.name)
                if value is None or value == "" or value == [] or value == {}:
                    errors.append(
                        {
                            "node_id": nid,
                            "field": field.name,
                            "message": f"field '{field.label}' is required",
                        }
                    )

            # agent custom mode requires model_id & system_prompt; agent_id uses existing agent
            if kind == "agent":
                agent_id = parameters.get("agent_id") or n.get("agent_id")
                if not agent_id and graph.get("kind") != "catalog_template":
                    # Only enforce model_id if not an empty legacy node
                    if not parameters.get("model_id") and not (n.get("config") == {} and n.get("parameters") is None):
                        errors.append(
                            {
                                "node_id": nid,
                                "field": "model_id",
                                "message": "custom agent requires a model",
                            }
                        )
                    if not parameters.get("system_prompt"):
                        errors.append(
                            {
                                "node_id": nid,
                                "field": "system_prompt",
                                "message": "custom agent requires a system prompt",
                            }
                        )
            # tool requires a tool name
            if kind == "tool" and not parameters.get("tool"):
                errors.append(
                    {
                        "node_id": nid,
                        "field": "tool",
                        "message": "tool node requires a tool to invoke",
                    }
                )
            # sub_workflow cannot be itself
            if kind == "sub_workflow":
                child_id = parameters.get("workflow_id")
                if child_id == nid:
                    errors.append(
                        {
                            "node_id": nid,
                            "field": "workflow_id",
                            "message": "sub_workflow cannot reference itself",
                        }
                    )

            # input_mapping source must exist and be upstream
            mapping = parameters.get("input_mapping") or []
            if isinstance(mapping, list):
                for item in mapping:
                    if not isinstance(item, dict):
                        continue
                    src = item.get("source_node_id")
                    if src and src not in ids:
                        errors.append(
                            {
                                "node_id": nid,
                                "field": "input_mapping",
                                "message": f"input_mapping source '{src}' does not exist",
                            }
                        )
                    elif src and src not in reachable.get(nid, set()):
                        errors.append(
                            {
                                "node_id": nid,
                                "field": "input_mapping",
                                "message": f"input_mapping source '{src}' is not upstream of this node",
                            }
                        )

            # output.include=selected requires selected_from
            if (
                kind == "output"
                and parameters.get("include") == "selected"
                and not parameters.get("selected_from")
            ):
                errors.append(
                    {
                        "node_id": nid,
                        "field": "selected_from",
                        "message": "output with 'selected' include requires selected_from nodes",
                    }
                )

        if errors:
            raise WorkflowValidationError(errors)

    async def _validate_agent_ownership(self, graph: dict, *, org_id: str) -> None:
        """Reject cross-org ``agent_id`` references on inherit-mode agent nodes.

        ``validate_graph`` is a sync structural check; this async helper adds
        the DB lookup that proves every inherited agent actually belongs to
        the org that owns the workflow. Without it, a user could save a
        workflow pointing at an agent from a different org and only hit the
        "agent not found" failure deep inside the worker.
        """
        from app.models.agent import Agent
        from sqlalchemy import select as _select

        errors: list[dict[str, str]] = []
        for n in graph.get("nodes", []) or []:
            if n.get("kind") != "agent":
                continue
            parameters = dict(n.get("parameters") or n.get("config") or {})
            mode = parameters.get("mode")
            legacy_agent_id = n.get("agent_id")
            # Catalog templates intentionally leave agent binding to runtime.
            if graph.get("kind") == "catalog_template":
                continue
            is_inherit = mode == "inherit" or (mode is None and legacy_agent_id)
            if not is_inherit:
                continue
            agent_id_value = parameters.get("agent_id") or legacy_agent_id
            if not agent_id_value:
                # Structural validator already raised this — skip silently.
                continue
            agent_row = await self.repo.db.scalar(
                _select(Agent.id).where(
                    Agent.id == agent_id_value,
                    Agent.org_id == org_id,
                )
            )
            if agent_row is None:
                errors.append(
                    {
                        "node_id": n.get("id", ""),
                        "field": "agent_id",
                        "message": f"agent '{agent_id_value}' is not in this organization",
                    }
                )
        if errors:
            raise WorkflowValidationError(errors)


def _field_visible(field, parameters: dict) -> bool:
    """Evaluate a field's ``display`` show/hide rules against current parameters.

    Mirrors the frontend renderer: a field is visible when its ``show`` rules
    match (all) and none of its ``hide`` rules match. No display rules = visible.
    """
    display = field.display
    if not display:
        return True
    if "show" in display:
        for key, values in display["show"].items():
            if parameters.get(key) not in values:
                return False
    if "hide" in display:
        for key, values in display["hide"].items():
            if parameters.get(key) in values:
                return False
    return True
