from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tools.types import ToolContext, ToolSpec
from app.models.mcp import McpServer, McpTool

_CI_KNOWLEDGE_COLLECTION_PREFIX = "ci-knowledge-"


def _rag_collection_scope_error(
    tool_name: str,
    collection: Any,
    org_id: str | None,
) -> str | None:
    """Reject cross-organization Customer Intelligence retrieval.

    The standalone RAG service authenticates the shared MCP connection, not
    the OpenAgent organization. The backend is therefore the trusted tenant
    boundary for agent/workflow calls. Generic RAG collections retain their
    existing behavior; only the org-scoped CI namespace is protected here.
    """
    if tool_name != "rag_search" or not isinstance(collection, str):
        return None
    if not collection.startswith(_CI_KNOWLEDGE_COLLECTION_PREFIX):
        return None
    expected = (
        f"{_CI_KNOWLEDGE_COLLECTION_PREFIX}{org_id}"
        if org_id
        else None
    )
    if collection != expected:
        return "error: rag_search collection is not accessible for this organization"
    return None


class McpClient:
    """Wraps a single MCP server. Connections are ephemeral — opened and torn
    down within the same call — because the `mcp` SDK's transports run an
    anyio task group bound to whichever asyncio task establishes them.
    FastAPI runs every request in its own task, so caching a connection
    across requests corrupts that task group on the next unrelated request
    (surfaces as a bare, message-less RuntimeError/ExceptionGroup deep in
    anyio's cancel-scope teardown). Reconnecting per call is the correct
    fix, not just a workaround: the SDK doesn't support cross-task reuse.
    The `mcp` package is imported lazily so the backend imports fine
    without it installed.
    """

    def __init__(self, server: McpServer):
        self.server = server

    def _transport(self):
        if self.server.transport == "stdio":
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=self.server.command or "",
                args=self.server.args or [],
                env=self.server.env or None,
            )
            return stdio_client(params)
        from mcp.client.sse import sse_client

        return sse_client(self.server.url, headers=self.server.headers or {})

    async def connect(self) -> None:
        # No persistent state to establish; list_tools() below does a real
        # round trip and will raise if the server is unreachable.
        await self.list_tools()

    async def list_tools(self) -> list[dict[str, Any]]:
        try:
            from mcp import ClientSession

            async with (
                self._transport() as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                resp = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": getattr(t, "description", "") or "",
                        "input_schema": getattr(t, "inputSchema", {}) or {},
                    }
                    for t in resp.tools
                ]
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("mcp package not installed; cannot connect to MCP servers") from e

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        from mcp import ClientSession

        async with (
            self._transport() as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, args)
            parts: list[str] = []
            for c in getattr(result, "content", []) or []:
                text = getattr(c, "text", None)
                if text is not None:
                    parts.append(text)
            return "\n".join(parts)

    async def disconnect(self) -> None:
        # Nothing persistent to tear down — kept for API compatibility.
        return None


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
        scope_error = _rag_collection_scope_error(
            tool_name,
            args.get("collection", "default"),
            ctx.org_id,
        )
        if scope_error:
            return scope_error
        stmt = select(McpServer).where(McpServer.id == server_id)
        if ctx.org_id:
            stmt = stmt.where(McpServer.org_id == ctx.org_id)
        res = await ctx.db.execute(stmt)
        server = res.scalar_one_or_none()
        if server is None:
            return "error: mcp server not found"
        if server.connection_status != "connected":
            return "error: mcp server is disconnected"
        try:
            return await get_mcp_manager().call_tool(server, tool_name, args)
        except Exception as e:  # noqa: BLE001
            return f"error calling mcp tool: {e}"

    return _run


async def build_mcp_tool_spec(
    name: str, db: AsyncSession, org_id: str | None = None
) -> ToolSpec | None:
    stmt = (
        select(McpTool)
        .join(McpServer, McpTool.server_id == McpServer.id)
        .where(
            McpTool.name == name,
            McpTool.enabled.is_(True),
            McpServer.connection_status == "connected",
        )
    )
    if org_id:
        stmt = stmt.where(McpServer.org_id == org_id)
    res = await db.execute(stmt)
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
