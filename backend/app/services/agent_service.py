from __future__ import annotations

from app.models.agent import Agent
from app.repositories.agent_repo import AgentRepository
from app.repositories.model_repo import ModelRepository


class AgentService:
    def __init__(self, db):
        self.repo = AgentRepository(db)
        self.model_repo = ModelRepository(db)

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Agent:
        m = await self.model_repo.get(org_id, data["model_id"])
        if m is None:
            raise ValueError("model not found")
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        if "allowed_risk_tiers" not in data or not data["allowed_risk_tiers"]:
            data["allowed_risk_tiers"] = ["safe", "read"]
        return await self.repo.create(Agent(**data))

    async def update(self, org_id: str, id: str, data: dict) -> Agent:
        a = await self.repo.get(org_id, id)
        if a is None:
            raise ValueError("agent not found")
        if "allowed_risk_tiers" in data and not data["allowed_risk_tiers"]:
            data.pop("allowed_risk_tiers")
        return await self.repo.update(a, data)

    async def delete(self, org_id: str, id: str) -> bool:
        return await self.repo.delete(org_id, id)

    async def list(self, org_id: str) -> list[Agent]:
        return await self.repo.list(org_id)

    async def get(self, org_id: str, id: str) -> Agent | None:
        return await self.repo.get(org_id, id)

    async def list_available_tools(self, org_id: str) -> list[dict]:
        from sqlalchemy import select

        from app.core.tools.registry import list_tools
        from app.models.mcp import McpServer, McpTool

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
                    "risk_tier": spec.risk_tier.value,
                }
            )
        res = await self.repo.db.execute(
            select(McpTool)
            .join(McpServer)
            .where(McpServer.org_id == org_id, McpTool.enabled.is_(True))
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
