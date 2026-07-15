"""stdio MCP transport entry point."""

from __future__ import annotations

from rag_service.mcp_server.server import create_mcp_server


def main() -> None:
    """Run the MCP server over stdio (blocks until stdin closes)."""
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
