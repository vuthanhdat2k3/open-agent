from __future__ import annotations

from app.models.workflow import Workflow
from app.repositories.workflow_repo import WorkflowRepository


class WorkflowService:
    def __init__(self, db):
        self.repo = WorkflowRepository(db)

    async def create(self, data: dict) -> Workflow:
        self.validate_graph(data.get("graph", {}))
        return await self.repo.create(Workflow(**data))

    async def update(self, id: str, data: dict) -> Workflow:
        wf = await self.repo.get(id)
        if wf is None:
            raise ValueError("workflow not found")
        if "graph" in data:
            self.validate_graph(data["graph"])
        return await self.repo.update(wf, data)

    async def delete(self, id: str) -> bool:
        return await self.repo.delete(id)

    async def list(self) -> list[Workflow]:
        return await self.repo.list()

    async def get(self, id: str) -> Workflow | None:
        return await self.repo.get(id)

    @staticmethod
    def validate_graph(graph: dict) -> None:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        if not any(n.get("kind") == "input" for n in nodes):
            raise ValueError("graph must have exactly one input node")
        input_count = sum(1 for n in nodes if n.get("kind") == "input")
        if input_count != 1:
            raise ValueError("graph must have exactly one input node")
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
