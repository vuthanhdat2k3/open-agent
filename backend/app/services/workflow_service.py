from __future__ import annotations

import json
import re

from sqlalchemy import select

from app.config import get_settings
from app.core.observability.llm_trace import ObservabilityContext, build_trace_context
from app.core.providers.factory import build_driver
from app.db.base import gen_id
from app.models.model import Model
from app.models.provider import Provider
from app.models.workflow import Workflow
from app.repositories.agent_repo import AgentRepository
from app.repositories.workflow_repo import WorkflowRepository

_GENERATE_SYSTEM_PROMPT = """You design workflow graphs for a multi-agent automation platform.

A workflow graph is JSON: {{"name": str, "description": str, "graph": {{"nodes": [...], "edges": [...]}}}}.

Node shape: {{"id": str, "kind": "input"|"agent"|"tool"|"merge"|"output"|"approval"|"scheduler"|"triager"|"integration", "label": str, "agent_id": str|null, "merge_mode": "all"|"any", "config": dict}}
- Exactly one entry trigger node:
  * "input" for on-demand interactive requests.
  * "scheduler" for recurring/scheduled automations (e.g. config: {{"cron": "0 6 * * *", "schedule_label": "Daily at 06:00"}}).
- At least one "output" node for returning results.
- "agent" nodes: if matching agents exist below, use their id. Otherwise set agent_id to null or the best matching agent.
- "integration" nodes: connect to Gmail, Google Calendar, Google Drive, or Webhook (e.g. config: {{"source": "google_drive"|"gmail"|"google_calendar"|"webhook"}}).
- "triager" nodes: filter, rank, or route items by urgency/category.
- "approval" nodes: pause for human sign-off before external side-effects (e.g. config: {{"tool_name": "send_email"}}).
- "merge" nodes: join parallel branches (merge_mode "all"|"any").

Edge shape: {{"from_": node_id, "to": node_id, "condition": str|null}}.

Examples:
1. "quét driver 6h sáng hàng ngày" (Scan Google Drive daily at 6am):
{{"name": "Daily 06:00 Google Drive Scanner", "description": "Scans Google Drive daily at 06:00, classifies updated documents, and synthesizes a digest.", "graph": {{"nodes": [{{"id": "trigger", "kind": "scheduler", "label": "Daily 06:00 Trigger", "config": {{"cron": "0 6 * * *", "schedule_label": "Daily at 06:00"}}}}, {{"id": "fetch_drive", "kind": "integration", "label": "Fetch Google Drive Documents", "config": {{"source": "google_drive"}}}}, {{"id": "triage", "kind": "triager", "label": "Filter New & Modified Files", "config": {{"policy": "filter_recent_docs"}}}}, {{"id": "analyzer", "kind": "agent", "label": "Document Intelligence Agent", "agent_id": null, "config": {{}}}}, {{"id": "output", "kind": "output", "label": "Drive Scan Digest", "config": {{}}}}], "edges": [{{"from_": "trigger", "to": "fetch_drive"}}, {{"from_": "fetch_drive", "to": "triage"}}, {{"from_": "triage", "to": "analyzer"}}, {{"from_": "analyzer", "to": "output"}}]}}}}

Available agents in this organization:
{agents}

Respond with ONLY the JSON object, no markdown fences, no commentary.
"""


class WorkflowService:
    def __init__(self, db):
        self.repo = WorkflowRepository(db)

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Workflow:
        self.validate_graph(data.get("graph", {}))
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

        valid_agent_ids = {a.id for a in agents}
        first_agent_id = agents[0].id if agents else None

        for node in graph.get("nodes", []):
            if node.get("kind") == "agent":
                aid = node.get("agent_id")
                if aid not in valid_agent_ids:
                    # Match by name if possible, or fallback to first available agent
                    matched = next(
                        (
                            a.id
                            for a in agents
                            if a.name.lower() in str(aid or "").lower()
                            or a.name.lower() in node.get("label", "").lower()
                        ),
                        first_agent_id,
                    )
                    node["agent_id"] = matched
            if node.get("merge_mode") is None:
                node.pop("merge_mode", None)
            if node.get("config") is None:
                node.pop("config", None)

        return {
            "name": result.get("name") or "Generated workflow",
            "description": result.get("description") or "",
            "graph": graph,
        }

    @staticmethod
    def validate_graph(graph: dict) -> None:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        if not any(n.get("kind") in ("input", "scheduler", "integration") for n in nodes):
            raise ValueError("graph must have at least one entry trigger node (input or scheduler)")
        entry_count = sum(1 for n in nodes if n.get("kind") in ("input", "scheduler"))
        if entry_count < 1 and not any(n.get("kind") == "integration" for n in nodes):
            raise ValueError("graph must have at least one entry trigger node (input or scheduler)")
        if not any(n.get("kind") in ("agent", "output") for n in nodes):
            raise ValueError("graph needs at least one agent or output node")
        ids = {n.get("id") for n in nodes}
        for e in edges:
            if e.get("from_") not in ids or e.get("to") not in ids:
                raise ValueError(f"edge references unknown node: {e}")
        # cycle detection (DFS)
        adj = {n["id"]: [] for n in nodes}
        for e in edges:
            adj[e["from_"]].append(e["to"])
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n["id"]: WHITE for n in nodes}

        def dfs(u: str) -> bool:
            color[u] = GRAY
            for v in adj[u]:
                if color[v] == GRAY:
                    return True
                if color[v] == WHITE and dfs(v):
                    return True
            color[u] = BLACK
            return False

        for n in nodes:
            if color[n["id"]] == WHITE and dfs(n["id"]):
                raise ValueError("graph contains a cycle")
