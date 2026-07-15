from __future__ import annotations

from sqlalchemy import select

from app.models.mcp import McpServer
from app.mcp.client import get_mcp_manager
from app.repositories.mcp_repo import McpRepository


class McpService:
    def __init__(self, db):
        self.repo = McpRepository(db)
        self.db = db

    async def create(self, data: dict) -> McpServer:
        name = data.get("name")
        if name:
            existing = (
                await self.db.execute(select(McpServer).where(McpServer.name == name))
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError(f"mcp server '{name}' already exists")
        srv = McpServer(**data)
        return await self.repo.create(srv)

    async def update(self, id: str, data: dict) -> McpServer:
        srv = await self.repo.get(id)
        if srv is None:
            raise ValueError("mcp server not found")
        return await self.repo.update(srv, data)

    async def delete(self, id: str) -> bool:
        await get_mcp_manager().disconnect(id)
        return await self.repo.delete(id)

    async def list(self) -> list[McpServer]:
        return await self.repo.list()

    async def get(self, id: str) -> McpServer | None:
        return await self.repo.get(id)

    async def connect(self, id: str) -> dict:
        srv = await self.repo.get(id)
        if srv is None:
            return {"ok": False, "message": "server not found"}
        try:
            mgr = get_mcp_manager()
            await mgr.connect(srv)
            tools = await mgr.get(srv).list_tools()
            await self.repo.replace_tools(id, tools)
            srv.connection_status = "connected"
            self.db.add(srv)
            await self.db.commit()
            return {
                "ok": True,
                "message": f"connected, {len(tools)} tools",
                "tool_count": len(tools),
            }
        except Exception as e:  # noqa: BLE001
            srv.connection_status = "error"
            self.db.add(srv)
            await self.db.commit()
            return {"ok": False, "message": f"error: {e}"}

    async def disconnect(self, id: str) -> dict:
        await get_mcp_manager().disconnect(id)
        srv = await self.repo.get(id)
        if srv:
            srv.connection_status = "disconnected"
            self.db.add(srv)
            await self.db.commit()
        return {"ok": True, "message": "disconnected"}
