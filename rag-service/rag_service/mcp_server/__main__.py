"""MCP server stdio entry point (``python -m rag_service.mcp_server``)."""

from __future__ import annotations

from rag_service.mcp_server.transport.stdio import main

if __name__ == "__main__":
    main()
