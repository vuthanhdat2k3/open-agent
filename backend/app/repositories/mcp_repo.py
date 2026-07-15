from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.mcp import McpServer, McpTool
from app.repositories.base import BaseRepository


class McpRepository(BaseRepository[McpServer]):
    def __init__(self, db):
        super().__init__(McpServer, db)

    async def list(self, limit: int = 100, offset: int = 0) -> list[McpServer]:
        # Eager-load tools so the relationship is populated inside the async
        # session; otherwise serialization (which runs after the session closes)
        # triggers a lazy load and raises MissingGreenlet. Also avoids N+1.
        res = await self.db.execute(
            select(McpServer)
            .options(selectinload(McpServer.tools))
            .order_by(McpServer.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def get(self, id: str) -> McpServer | None:
        res = await self.db.execute(
            select(McpServer).options(selectinload(McpServer.tools)).where(McpServer.id == id)
        )
        return res.scalar_one_or_none()

    async def list_tools(self, server_id: str) -> list[McpTool]:
        from sqlalchemy import select

        res = await self.db.execute(
            select(McpTool).where(McpTool.server_id == server_id)
        )
        return list(res.scalars().all())

    async def replace_tools(self, server_id: str, tools: list[dict]) -> None:
        from sqlalchemy import delete

        await self.db.execute(delete(McpTool).where(McpTool.server_id == server_id))
        for t in tools:
            self.db.add(
                McpTool(
                    server_id=server_id,
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("input_schema", {}),
                    enabled=True,
                )
            )
        await self.db.commit()
