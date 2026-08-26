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
- Exactly one entry trigger node ("input" for on-demand requests, or "scheduler" for recurring/periodic automations).
- At least one "output" node for returning results.
- "agent" nodes MUST use an agent_id from the list below — never invent one.
- "scheduler" nodes define automated recurrence or timer triggers (e.g. config: {{"cron": "0 7 * * 1-5", "label": "Weekdays at 07:30"}}).
- "triager" nodes classify, filter, or branch incoming requests into different paths based on intent or urgency.
- "integration" nodes connect to Gmail, Google Calendar, Google Drive, or Webhooks (e.g. config: {{"source": "gmail"}}).
- "approval" nodes pause execution for human sign-off before proceeding with sensitive actions.
- Use "merge" nodes (merge_mode "all"|"any") to join parallel branches back together.
Edge shape: {{"from_": node_id, "to": node_id, "condition": str|null}}.

Available agents in this organization:
{agents}

Design a graph that fulfils the user's request. Prefer running independent steps in parallel
(fan-out to multiple agent nodes from the same source, fan-in via a merge node) over a purely
sequential chain when the steps do not depend on each other.

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
        if not agents:
            raise ValueError("create at least one agent before generating a workflow")
        agents_desc = "\n".join(
            f'- id="{a.id}" name="{a.name}" kind={a.kind}: {a.description or "(no description)"}'
            for a in agents
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
        for node in graph.get("nodes", []):
            if node.get("kind") == "agent" and node.get("agent_id") not in valid_agent_ids:
                raise ValueError(f"generated graph references unknown agent_id: {node.get('agent_id')}")
            # The model sometimes emits explicit nulls for optional fields; drop them so
            # pydantic falls back to field defaults instead of failing validation
            # (merge_mode is a non-nullable Literal on the GraphNode schema).
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
