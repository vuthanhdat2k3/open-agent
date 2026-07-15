from __future__ import annotations

from app.models.agent import Agent
from app.repositories.agent_repo import AgentRepository
from app.repositories.model_repo import ModelRepository


class AgentService:
    def __init__(self, db):
        self.repo = AgentRepository(db)
        self.model_repo = ModelRepository(db)

    async def create(self, data: dict) -> Agent:
        m = await self.model_repo.get(data["model_id"])
        if m is None:
            raise ValueError("model not found")
        return await self.repo.create(Agent(**data))

    async def update(self, id: str, data: dict) -> Agent:
        a = await self.repo.get(id)
        if a is None:
            raise ValueError("agent not found")
        return await self.repo.update(a, data)

    async def delete(self, id: str) -> bool:
        return await self.repo.delete(id)

    async def list(self) -> list[Agent]:
        return await self.repo.list()

    async def get(self, id: str) -> Agent | None:
        return await self.repo.get(id)

    async def list_available_tools(self) -> list[dict]:
        from app.core.tools.registry import list_tools
        from sqlalchemy import select

        from app.models.mcp import McpTool

        seen: set[str] = set()
        out: list[dict] = []
        for spec in list_tools():
            if spec.name in seen:
                continue
            seen.add(spec.name)
            out.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "available": True,
                }
            )
        res = await self.repo.db.execute(
            select(McpTool).where(McpTool.enabled.is_(True))
        )
        for t in res.scalars().all():
            if t.name in seen:
                continue
            seen.add(t.name)
            out.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "available": True,
                }
            )
        return out
