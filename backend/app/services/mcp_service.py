from __future__ import annotations

from sqlalchemy import select

from app.mcp.client import get_mcp_manager
from app.models.mcp import McpServer
from app.repositories.mcp_repo import McpRepository


class McpService:
    def __init__(self, db):
        self.repo = McpRepository(db)
        self.db = db

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> McpServer:
        name = data.get("name")
        if name:
            existing = (
                await self.db.execute(
                    select(McpServer).where(McpServer.org_id == org_id, McpServer.name == name)
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError(f"mcp server '{name}' already exists")
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        srv = McpServer(**data)
        created = await self.repo.create(srv)
        return await self.repo.get(org_id, created.id) or created

    async def update(self, org_id: str, id: str, data: dict) -> McpServer:
        srv = await self.repo.get(org_id, id)
        if srv is None:
            raise ValueError("mcp server not found")
        updated = await self.repo.update(srv, data)
        return await self.repo.get(org_id, updated.id) or updated

    async def delete(self, org_id: str, id: str) -> bool:
        await get_mcp_manager().disconnect(id)
        return await self.repo.delete(org_id, id)

    async def list(self, org_id: str) -> list[McpServer]:
        return await self.repo.list(org_id)

    async def get(self, org_id: str, id: str) -> McpServer | None:
        return await self.repo.get(org_id, id)

    async def connect(self, org_id: str, id: str) -> dict:
        srv = await self.repo.get(org_id, id)
        if srv is None:
            return {"ok": False, "message": "server not found"}
        try:
            mgr = get_mcp_manager()
            await mgr.disconnect(id)
            await mgr.connect(srv)
            tools = await mgr.get(srv).list_tools()
            srv.connection_status = "connected"
            self.db.add(srv)
            await self.db.commit()
            await self.db.refresh(srv)
            await self.repo.replace_tools(id, tools)
            return {
                "ok": True,
                "message": f"connected, {len(tools)} tools",
                "tool_count": len(tools),
            }
        except Exception as e:  # noqa: BLE001
            await self._set_status(org_id, id, "error")
            return {"ok": False, "message": f"error: {e}"}

    async def _set_status(self, org_id: str, id: str, status: str) -> None:
        from sqlalchemy import update

        await self.db.execute(
            update(McpServer)
            .where(McpServer.org_id == org_id, McpServer.id == id)
            .values(connection_status=status)
        )
        await self.db.commit()

    async def disconnect(self, org_id: str, id: str) -> dict:
        await get_mcp_manager().disconnect(id)
        srv = await self.repo.get(org_id, id)
        if srv:
            srv.connection_status = "disconnected"
            self.db.add(srv)
            await self.db.commit()
        return {"ok": True, "message": "disconnected"}
