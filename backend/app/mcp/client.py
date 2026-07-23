from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tools.types import ToolContext, ToolSpec
from app.models.mcp import McpServer, McpTool


class McpClient:
    """Wraps a single MCP server connection. The `mcp` package is imported
    lazily so the backend imports fine without it installed."""

    def __init__(self, server: McpServer):
        self.server = server
        self._conn: dict[str, Any] | None = None

    async def connect(self) -> None:
        if self._conn is not None:
            return
        transport = self.server.transport
        try:
            if transport == "stdio":
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                params = StdioServerParameters(
                    command=self.server.command or "",
                    args=self.server.args or [],
                    env=self.server.env or None,
                )
                ctx = stdio_client(params)
                read, write = await ctx.__aenter__()
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                self._conn = {"ctx": ctx, "session": session}
            else:
                from mcp import ClientSession
                from mcp.client.sse import sse_client

                ctx = sse_client(self.server.url, headers=self.server.headers or {})
                read, write = await ctx.__aenter__()
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                self._conn = {"ctx": ctx, "session": session}
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "mcp package not installed; cannot connect to MCP servers"
            ) from e

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.connect()
        assert self._conn is not None
        resp = await self._conn["session"].list_tools()
        out: list[dict[str, Any]] = []
        for t in resp.tools:
            out.append(
                {
                    "name": t.name,
                    "description": getattr(t, "description", "") or "",
                    "input_schema": getattr(t, "inputSchema", {}) or {},
                }
            )
        return out

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        await self.connect()
        assert self._conn is not None
        result = await self._conn["session"].call_tool(name, args)
        parts: list[str] = []
        for c in getattr(result, "content", []) or []:
            text = getattr(c, "text", None)
            if text is not None:
                parts.append(text)
        return "\n".join(parts)

    async def disconnect(self) -> None:
        conn = self._conn
        self._conn = None
        if not conn:
            return
        try:
            await conn["session"].__aexit__(None, None, None)
        except Exception:  # noqa: BLE001, SIM105
            pass
        try:
            await conn["ctx"].__aexit__(None, None, None)
        except Exception:  # noqa: BLE001, SIM105
            pass


class McpManager:
    def __init__(self) -> None:
        self._clients: dict[str, McpClient] = {}

    def get(self, server: McpServer) -> McpClient:
        client = self._clients.get(server.id)
        if client is None:
            client = McpClient(server)
            self._clients[server.id] = client
        return client

    async def connect(self, server: McpServer) -> None:
        await self.get(server).connect()

    async def call_tool(self, server: McpServer, name: str, args: dict[str, Any]) -> str:
        return await self.get(server).call_tool(name, args)

    async def disconnect(self, server_id: str) -> None:
        client = self._clients.pop(server_id, None)
        if client is not None:
            await client.disconnect()


_MANAGER: McpManager | None = None


def get_mcp_manager() -> McpManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = McpManager()
    return _MANAGER


def _make_mcp_run(server_id: str, tool_name: str):
    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        res = await ctx.db.execute(
            select(McpServer).where(McpServer.id == server_id)
        )
        server = res.scalar_one_or_none()
        if server is None:
            return "error: mcp server not found"
        try:
            return await get_mcp_manager().call_tool(server, tool_name, args)
        except Exception as e:  # noqa: BLE001
            return f"error calling mcp tool: {e}"

    return _run


async def build_mcp_tool_spec(name: str, db: AsyncSession) -> ToolSpec | None:
    res = await db.execute(
        select(McpTool).where(McpTool.name == name, McpTool.enabled.is_(True))
    )
    tool = res.scalar_one_or_none()
    if tool is None:
        return None
    res = await db.execute(select(McpServer).where(McpServer.id == tool.server_id))
    server = res.scalar_one_or_none()
    if server is None:
        return None
    return ToolSpec(
        name=name,
        description=tool.description or f"MCP tool {name}",
        input_schema=tool.input_schema or {"type": "object", "properties": {}},
        run=_make_mcp_run(server.id, name),
    )
