from __future__ import annotations

import json
import re

import structlog
from simpleeval import simple_eval
from sqlalchemy import select

from app.config import get_settings
from app.core.observability.llm_trace import ObservabilityContext, build_trace_context
from app.core.providers.factory import build_driver
from app.core.workflow.node_definitions import get_node_definition
from app.core.workflow.templates import SYSTEM_WORKFLOW_BLUEPRINTS, SystemWorkflowBlueprint
from app.db.base import gen_id, utc_now
from app.models.model import Model
from app.models.provider import Provider
from app.models.workflow import Workflow
from app.repositories.agent_repo import AgentRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.schemas.workflow import WorkflowValidationError

logger = structlog.get_logger(__name__)

_GENERATE_SYSTEM_PROMPT = """You design workflow graphs for a multi-agent automation platform.

A workflow graph is JSON: {{"name": str, "description": str, "graph": {{"nodes": [...], "edges": [...]}}}}.

Node shape: {{"id": str, "kind": "input"|"agent"|"tool"|"merge"|"output"|"approval"|"scheduler"|"triager"|"integration"|"sub_workflow", "label": str, "agent_id": str|null, "merge_mode": "all"|"any", "parameters": dict}}
- Exactly one entry trigger node:
  * "input" for on-demand interactive requests (parameters: {{"input_field": str}}).
  * "scheduler" for recurring/scheduled automations (parameters: {{"frequency": "daily"|"weekdays"|"weekly"|"hourly"|"custom", "time": "HH:MM", "days_of_week": ["mon"...], "custom_cron": "0 6 * * *"}}).
- At least one "output" node for returning results — parameters: {{"include": "all_inputs", "save_as_file": bool, "file_name": str}}. Set "save_as_file": true + a "file_name" (e.g. "workflow-outputs/my-brief") only when the user explicitly wants the result saved as a file; every run always notifies whoever triggered it regardless of this setting, so it is NOT needed just to "notify" someone.
- "agent" nodes: if matching agents exist below, use their id with mode "inherit". ALWAYS also set an "instructions" string — the specific task for THIS step (e.g. what to search for, what format to produce); it is layered onto the upstream data as the agent's task for this run, on top of the agent's own persona. Otherwise (no matching agent) set parameters {{"mode": "custom", "system_prompt": str, "model_id": null}} (the system will bind a model).
- "integration" nodes: connect to real data — parameters: {{"source": "google_drive"|"gmail"|"google_calendar"|"webhook", "operation": "list_new"|"search"|"list_events"|"list_files", "max_results": 20}}. There is no time-range filter field for calendar/drive beyond max_results.
- "triager" nodes: classify upstream text into EXACTLY ONE of a fixed category list — parameters: {{"mode": "llm", "categories": "sales, support, spam"}} or {{"mode": "rules", "rules": [{{"pattern": str, "category": str}}]}}. It cannot deduplicate, cluster, or rank a list of items — for that, give the downstream "agent" node's "instructions" that job instead and skip the triager.
- "tool" nodes: invoke a registered tool — parameters: {{"tool": str, "arguments": dict}}.
- "approval" nodes: pause for human sign-off — parameters: {{"title": str, "instructions": str, "approver_user_ids": [str]|[], "timeout_minutes": int}}. Empty approver_user_ids = anyone with approval permission may decide; timeout_minutes 0 = never auto-decline.
- "sub_workflow" nodes: run another workflow — parameters: {{"workflow_id": str}}.
- "merge" nodes: join parallel branches (merge_mode "all"|"any").

Use "parameters" (NOT "config") for node configuration. Do not invent parameter names beyond what is listed above for each kind — unrecognized keys are silently dropped.

Edge shape: {{"from_": node_id, "to": node_id, "condition": str|null}}.

Examples:
1. "quét driver 6h sáng hàng ngày" (Scan Google Drive daily at 6am):
{{"name": "Daily 06:00 Google Drive Scanner", "description": "Scans Google Drive daily at 06:00, classifies updated documents, and synthesizes a digest.", "graph": {{"nodes": [{{"id": "trigger", "kind": "scheduler", "label": "Daily 06:00 Trigger", "parameters": {{"frequency": "daily", "time": "06:00"}}}}, {{"id": "fetch_drive", "kind": "integration", "label": "Fetch Google Drive Documents", "parameters": {{"source": "google_drive", "operation": "list_files"}}}}, {{"id": "triage", "kind": "triager", "label": "Filter New & Modified Files", "parameters": {{"mode": "llm", "categories": "updated, unchanged"}}}}, {{"id": "analyzer", "kind": "agent", "label": "Document Intelligence Agent", "parameters": {{"mode": "custom", "system_prompt": "Summarize the documents."}}}}, {{"id": "output", "kind": "output", "label": "Drive Scan Digest", "parameters": {{"include": "all_inputs"}}}}], "edges": [{{"from_": "trigger", "to": "fetch_drive"}}, {{"from_": "fetch_drive", "to": "triage"}}, {{"from_": "triage", "to": "analyzer"}}, {{"from_": "analyzer", "to": "output"}}]}}}}

Available agents in this organization:
{agents}

Respond with ONLY the JSON object, no markdown fences, no commentary.
"""


def strip_unknown_node_parameters(graph: dict, *, org_id: str = "") -> list[dict]:
    """Drop any node `parameters` key not declared in that node kind's
    ``NODE_DEFINITIONS`` schema, mutating ``graph`` in place.

    LLM-generated graphs (and hand-authored ones) sometimes invent
    plausible-sounding field names — e.g. an "agent" node's own
    "delivery_channel" — that the engine has never read, silently doing
    nothing. Stripping them here surfaces the mismatch in the log instead of
    shipping a workflow with dead configuration. Returns the list of
    {node_id, kind, keys} entries that were stripped, for logging/testing.
    """
    stripped: list[dict] = []
    for node in graph.get("nodes", []):
        parameters = node.get("parameters")
        if not isinstance(parameters, dict):
            continue
        definition = get_node_definition(node.get("kind"))
        if definition is None:
            continue
        valid_names = {f.name for f in definition.fields}
        unknown = [k for k in parameters if k not in valid_names]
        for key in unknown:
            parameters.pop(key, None)
        if unknown:
            stripped.append({"node_id": node.get("id"), "kind": node.get("kind"), "keys": unknown})
            logger.warning(
                "workflow_generate_stripped_unknown_params",
                org_id=org_id,
                node_id=node.get("id"),
                kind=node.get("kind"),
                keys=unknown,
            )
    return stripped


class WorkflowService:
    def __init__(self, db):
        self.repo = WorkflowRepository(db)

    def _build_virtual_workflow(
        self,
        org_id: str,
        blueprint: SystemWorkflowBlueprint,
    ) -> Workflow:
        now = utc_now()
        return Workflow(
            id=blueprint.id,
            org_id=org_id,
            created_by_user_id=None,
            name=blueprint.name,
            description=blueprint.description,
            graph=dict(blueprint.graph),
            template_key=blueprint.key,
            is_customized=False,
            created_at=now,
            updated_at=now,
        )

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Workflow:
        self.validate_graph(data.get("graph", {}))
        await self._validate_agent_ownership(data.get("graph", {}), org_id=org_id)
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        return await self.repo.create(Workflow(**data))

    async def update(
        self, org_id: str, id: str, data: dict, user_id: str | None = None
    ) -> Workflow:
        wf = await self.repo.db.scalar(
            select(Workflow).where(Workflow.id == id, Workflow.org_id == org_id).with_for_update()
        )
        if wf is None:
            # Check if this is a System Blueprint being forked on write
            matched_blueprint = None
            for bp in SYSTEM_WORKFLOW_BLUEPRINTS.values():
                if (
                    bp.id == id
                    or bp.key == id
                    or bp.name.lower() == id.lower()
                    or bp.key == id.replace("sys-wf-", "")
                ):
                    matched_blueprint = bp
                    break
            if matched_blueprint is not None:
                # Check if an existing override exists by template_key
                existing_override = await self.repo.db.scalar(
                    select(Workflow).where(
                        Workflow.org_id == org_id,
                        Workflow.template_key == matched_blueprint.key,
                    ).with_for_update()
                )
                if existing_override is not None:
                    wf = existing_override
                else:
                    graph_data = data.get("graph") or dict(matched_blueprint.graph)
                    if "graph" in data:
                        self.validate_graph(graph_data)
                        await self._validate_agent_ownership(graph_data, org_id=org_id)
                    base_data = {
                        "name": data.get("name") or matched_blueprint.name,
                        "description": data.get("description") if "description" in data else matched_blueprint.description,
                        "graph": graph_data,
                        "template_key": matched_blueprint.key,
                        "is_customized": True,
                    }
                    return await self.create(org_id, base_data, user_id)
            else:
                raise ValueError("workflow not found")

        if "graph" in data:
            self.validate_graph(data["graph"])
            await self._validate_agent_ownership(data["graph"], org_id=org_id)
        if getattr(wf, "template_key", None):
            data["is_customized"] = True
        return await self.repo.update(wf, data)

    async def delete(self, org_id: str, id: str) -> bool:
        wf = await self.repo.get(org_id, id)
        if wf and getattr(wf, "template_key", None) in SYSTEM_WORKFLOW_BLUEPRINTS and not getattr(wf, "is_customized", True):
            raise ValueError("System template workflows cannot be deleted. Reset or modify them instead.")
        return await self.repo.delete(org_id, id)

    async def reset_to_template(self, org_id: str, id: str) -> Workflow:
        """Reset a workflow override back to the system blueprint default, deleting the custom DB record."""
        # Find matched blueprint
        matched_blueprint = None
        for bp in SYSTEM_WORKFLOW_BLUEPRINTS.values():
            if (
                bp.id == id
                or bp.key == id
                or bp.name.lower() == id.lower()
                or bp.key == id.replace("sys-wf-", "")
            ):
                matched_blueprint = bp
                break

        # Check DB row by id or template_key
        db_wf = await self.repo.get(org_id, id)
        if db_wf is None and matched_blueprint is not None:
            db_wf = await self.repo.db.scalar(
                select(Workflow).where(
                    Workflow.org_id == org_id,
                    Workflow.template_key == matched_blueprint.key,
                )
            )

        if db_wf is not None:
            if not matched_blueprint and db_wf.template_key:
                matched_blueprint = SYSTEM_WORKFLOW_BLUEPRINTS.get(db_wf.template_key)
            if not matched_blueprint:
                raise ValueError("Workflow is a custom workflow and cannot be reset to a system template")

            # Delete the workflow DB record
            await self.repo.db.delete(db_wf)
            await self.repo.db.commit()

        if matched_blueprint is None:
            raise ValueError("Template blueprint not found")

        return self._build_virtual_workflow(org_id, matched_blueprint)

    async def list(self, org_id: str, created_by_user_id: str | None = None) -> list[Workflow]:
        return await self.repo.list(org_id, created_by_user_id=created_by_user_id)

    async def get(self, org_id: str, id: str) -> Workflow | None:
        # 1. Try DB lookup by exact ID
        wf = await self.repo.get(org_id, id)
        if wf is not None:
            return wf

        # 2. Check if ID matches a System Blueprint (by exact ID, key, name, or sys-wf-*)
        matched_blueprint = None
        for bp in SYSTEM_WORKFLOW_BLUEPRINTS.values():
            if (
                bp.id == id
                or bp.key == id
                or bp.name.lower() == id.lower()
                or bp.key == id.replace("sys-wf-", "")
            ):
                matched_blueprint = bp
                break

        if matched_blueprint is not None:
            # Look-through: Check if org has an override in DB for this template_key
            override = await self.repo.db.scalar(
                select(Workflow).where(
                    Workflow.org_id == org_id,
                    Workflow.template_key == matched_blueprint.key,
                )
            )
            if override is not None:
                return override
            return self._build_virtual_workflow(org_id, matched_blueprint)

        # 3. Try DB lookup by exact name
        by_name = await self.repo.db.scalar(
            select(Workflow).where(Workflow.org_id == org_id, Workflow.name == id)
        )
        if by_name is not None:
            return by_name

        return None

    async def ensure_persisted(self, org_id: str, id: str, user_id: str | None = None) -> Workflow | None:
        """Ensure a workflow exists in the DB (materializing virtual blueprints on-demand if needed)."""
        wf = await self.get(org_id, id)
        if wf is None:
            return None
        # If it's already a real DB record
        if not getattr(wf, "id", "").startswith("sys-wf-"):
            return wf
        # It's a virtual blueprint - find the blueprint definition
        matched_blueprint = None
        for bp in SYSTEM_WORKFLOW_BLUEPRINTS.values():
            if (
                bp.id == wf.id
                or bp.key == wf.template_key
                or bp.name.lower() == wf.name.lower()
            ):
                matched_blueprint = bp
                break
        if matched_blueprint is None:
            return wf

        # Check again if an override was created concurrently
        override = await self.repo.db.scalar(
            select(Workflow).where(
                Workflow.org_id == org_id,
                Workflow.template_key == matched_blueprint.key,
            )
        )
        if override is not None:
            return override

        base_data = {
            "name": matched_blueprint.name,
            "description": matched_blueprint.description,
            "graph": dict(matched_blueprint.graph),
            "template_key": matched_blueprint.key,
            "is_customized": False,
        }
        return await self.create(org_id, base_data, user_id)

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

        strip_unknown_node_parameters(graph, org_id=org_id)

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
        seen_edges: set[tuple[str, str]] = set()
        for e in edges:
            if e.get("from_") not in ids or e.get("to") not in ids:
                errors.append(
                    {
                        "node_id": "",
                        "field": "edge",
                        "message": f"edge references unknown node: {e}",
                    }
                )
            # Reject parallel edges between the same two nodes. The edge id
            # serialized to the frontend is "{from_}->{to}#{index}", so two
            # edges sharing a (from_, to) pair would be indistinguishable on
            # select/delete (M13). The canvas onConnect already de-dupes on
            # drag-connect; blocking it at validation keeps imported/template
            # graphs consistent too.
            pair = (e.get("from_"), e.get("to"))
            if pair in seen_edges:
                errors.append(
                    {
                        "node_id": e.get("from_", ""),
                        "field": "edge",
                        "message": f"duplicate edge between the same nodes: {e.get('from_')} -> {e.get('to')}",
                    }
                )
            else:
                seen_edges.add(pair)
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
        from sqlalchemy import select as _select

        from app.models.agent import Agent

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
