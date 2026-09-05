from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.mcp import McpServer, McpTool

# Real tool names exposed by rag-service's MCP server
# (rag-service/rag_service/mcp_server/server.py). Two dead names
# (`rag_graph_search`, `rag_delete_collection`) previously appeared only in
# dev-seed data / a stale blueprint reference and do not exist on the wire -
# they are intentionally absent here.
#
# risk_tier / requires_approval mirror how these tools are actually used by
# the System Agent Blueprints (see app/core/agents/templates.py):
# - rag_search / rag_list_collections are read-only lookups.
# - rag_ingest_* write into the org's knowledge base but do not destroy data.
# - rag_delete_document is destructive and always requires approval.
_RAG_TOOL_DEFS: tuple[tuple[str, str, str, bool], ...] = (
    ("rag_search", "Hybrid BM25 + semantic search over a knowledge base collection.", "read", False),
    ("rag_ingest_url", "Ingest a web URL into a knowledge base collection.", "write", False),
    ("rag_ingest_text", "Ingest raw text into a knowledge base collection.", "write", False),
    ("rag_ingest_file", "Ingest an uploaded file into a knowledge base collection.", "write", False),
    ("rag_list_collections", "List all knowledge base collections.", "read", False),
    ("rag_delete_document", "Permanently delete a document and its chunks.", "dangerous", True),
)


async def ensure_rag_mcp_server(db: AsyncSession, org_id: str) -> McpServer | None:
    """Idempotently register the shared rag-service as this org's RAG MCP
    server, with its 6 real tools pre-classified by risk tier.

    Without this, every System Agent Blueprint that carries `rag_search` /
    `rag_ingest_*` / etc. silently no-ops: those tools only resolve at
    runtime via `build_mcp_tool_spec()` (app/mcp/client.py), which requires a
    connected `McpServer` + enabled `McpTool` row scoped to the org. Call
    this once at org-creation time so RAG tools work out of the box.

    Marked `connection_status="connected"` directly (skipping the real
    handshake in `McpService.connect()`): the shared rag-service is a
    same-deployment sidecar the platform operator controls, not a
    user-supplied MCP endpoint that needs a live reachability check before
    being trusted. If it is actually unreachable, individual tool calls
    surface that as a normal tool-execution error instead of blocking org
    creation on it.
    """
    settings = get_settings()
    existing = (
        await db.execute(
            select(McpServer).where(
                McpServer.org_id == org_id,
                McpServer.name == settings.rag_mcp_server_name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    server = McpServer(
        org_id=org_id,
        name=settings.rag_mcp_server_name,
        transport="sse",
        url=settings.rag_mcp_url,
        headers={"X-API-Key": settings.rag_api_key} if settings.rag_api_key else {},
        connection_status="connected",
    )
    db.add(server)
    await db.flush()

    for name, description, risk_tier, requires_approval in _RAG_TOOL_DEFS:
        db.add(
            McpTool(
                server_id=server.id,
                name=name,
                description=description,
                input_schema={"type": "object", "properties": {}},
                enabled=True,
                risk_tier=risk_tier,
                requires_approval=requires_approval,
            )
        )
    return server
