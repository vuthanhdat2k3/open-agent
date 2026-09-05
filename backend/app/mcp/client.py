from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.models.mcp import McpServer, McpTool
from app.services.rag_collections import resolve_rag_collection

_CI_KNOWLEDGE_COLLECTION_PREFIX = "ci-knowledge-"
_ORG_COLLECTION_PREFIX = "org-"
# Generic RAG tools that read/write a specific collection and therefore need
# tenant isolation. `rag_list_collections` takes no collection argument and
# is filtered separately (see `_filter_collection_list_output`).
_RAG_COLLECTION_TOOLS = {
    "rag_search",
    "rag_ingest_url",
    "rag_ingest_text",
    "rag_ingest_file",
    "rag_delete_document",
}


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


def _namespace_rag_collection(collection: Any, org_id: str | None) -> Any:
    """Isolate generic RAG collections per organization (shared/org scope).

    The standalone rag-service has no tenant concept of its own — its
    ``Collection`` rows are keyed only by name. Every organization sharing
    one rag-service instance/MCP connection would otherwise read and write
    the exact same collection (e.g. the literal ``"default"``), leaking
    document content across tenants. Namespacing the collection name here,
    at the trusted OpenAgent boundary, isolates each org without requiring
    any change to the rag-service. The CI knowledge namespace already
    carries its own per-org prefix (``ci-knowledge-<org_id>``) and is left
    untouched. See ``resolve_rag_collection`` for the further per-user
    (personal) scope used by plain ``user`` callers.
    """
    return resolve_rag_collection(collection, org_id, personal_user_id=None)


_RAG_LIST_COLLECTIONS_BLOCK_RE = re.compile(
    r"\n  (\S+)\n    Documents:[^\n]*\n    Last updated:[^\n]*"
)


def _filter_rag_collections_output(text: str, org_id: str | None) -> str:
    """Strip other organizations' collection names out of rag_list_collections.

    ``rag_list_collections`` has no ``collection`` argument to namespace, and
    the rag-service returns every collection on the shared instance in one
    plaintext listing. Without filtering here, an org would see the names
    (not content, but still tenant metadata) of every other org's
    collections. We only reveal collections this org could actually reach
    via the other RAG tools: its own namespaced prefix, or its CI knowledge
    collection.
    """
    if not org_id or not text.startswith("Collections ("):
        return text
    own_prefix = f"{_ORG_COLLECTION_PREFIX}{org_id}-"
    ci_name = f"{_CI_KNOWLEDGE_COLLECTION_PREFIX}{org_id}"
    visible = [
        match.group(0)
        for match in _RAG_LIST_COLLECTIONS_BLOCK_RE.finditer(text)
        if match.group(1).startswith(own_prefix) or match.group(1) == ci_name
    ]
    if not visible:
        return "No collections found."
    return f"Collections ({len(visible)}):\n" + "".join(visible)


def _merge_rag_search_results(shared_text: str, personal_text: str) -> str:
    """Combine a plain user's shared-org and personal `rag_search` results.

    Both calls hit the same rag-service tool independently (see
    `_make_mcp_run`), so this only needs to present both plaintext blocks to
    the model — it never parses rag-service's result format, which is free
    to change without breaking isolation here.
    """
    empty_prefixes = ("No results found", "Search error")
    sections = []
    if not shared_text.startswith(empty_prefixes):
        sections.append(f"=== Organization-shared results ===\n{shared_text}")
    if not personal_text.startswith(empty_prefixes):
        sections.append(f"=== Your personal results ===\n{personal_text}")
    if not sections:
        return shared_text
    return "\n\n".join(sections)


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
    async def _call(args: dict[str, Any], ctx: ToolContext) -> str:
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

    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        base_collection = args.get("collection", "default")
        scope_error = _rag_collection_scope_error(tool_name, base_collection, ctx.org_id)
        if scope_error:
            return scope_error

        if tool_name in _RAG_COLLECTION_TOOLS:
            # A plain `user` (no elevated role) is scoped to their own
            # personal collection; operator/org_admin/platform_admin stay on
            # the shared org collection — mirrors `PrincipalContext.owner_user_id`
            # (personal only for role=="user"). Role/user_id come from the
            # trusted server-side context, never from the LLM's tool args.
            role = ctx.authorization.role if ctx.authorization else None
            is_plain_user = role == "user" and bool(ctx.user_id)

            if tool_name == "rag_search" and is_plain_user:
                shared_collection = resolve_rag_collection(
                    base_collection, ctx.org_id, personal_user_id=None
                )
                personal_collection = resolve_rag_collection(
                    base_collection, ctx.org_id, personal_user_id=ctx.user_id
                )
                shared_result, personal_result = await asyncio.gather(
                    _call({**args, "collection": shared_collection}, ctx),
                    _call({**args, "collection": personal_collection}, ctx),
                )
                return _merge_rag_search_results(shared_result, personal_result)

            target_collection = resolve_rag_collection(
                base_collection,
                ctx.org_id,
                personal_user_id=ctx.user_id if is_plain_user else None,
            )
            # Copy rather than mutate the caller's dict: agent_loop/workflow
            # engine may log or replay the original args after this call.
            args = {**args, "collection": target_collection}

        result = await _call(args, ctx)
        if tool_name == "rag_list_collections":
            result = _filter_rag_collections_output(result, ctx.org_id)
        return result

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
    try:
        risk_tier = RiskTier(str(tool.risk_tier))
    except ValueError:
        risk_tier = RiskTier.dangerous
    return ToolSpec(
        name=name,
        description=tool.description or f"MCP tool {name}",
        input_schema=tool.input_schema or {"type": "object", "properties": {}},
        run=_make_mcp_run(server.id, name),
        risk_tier=risk_tier,
        requires_approval=bool(tool.requires_approval),
    )
