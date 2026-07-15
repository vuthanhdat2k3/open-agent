"""SSE / HTTP MCP transport package."""

from __future__ import annotations

from rag_service.mcp_server.transport.sse import create_sse_app

__all__ = ["create_sse_app"]
