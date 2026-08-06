from __future__ import annotations

import json
from typing import Any

from app.config import get_settings


class CustomerIntelligenceMcpError(RuntimeError):
    pass


def _server():
    from app.models.mcp import McpServer

    settings = get_settings()
    return McpServer(
        name=settings.ci_mcp_server_name,
        transport=settings.ci_mcp_transport,
        command=settings.ci_mcp_command,
        args=settings.ci_mcp_args,
        url=settings.ci_mcp_url,
        headers={},
    )


def _decode(raw: str) -> Any:
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CustomerIntelligenceMcpError("MCP returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise CustomerIntelligenceMcpError("MCP returned an invalid result")
    if result.get("status") != "ok":
        message = "; ".join(result.get("warnings") or []) or "MCP tool failed"
        raise CustomerIntelligenceMcpError(message)
    return result.get("data")


async def call_customer_intelligence_mcp(tool_name: str, args: dict[str, Any]) -> Any:
    """Call the stateless CI MCP server; credentials remain per-call only."""
    from app.mcp.client import McpClient

    return _decode(await McpClient(_server()).call_tool(tool_name, args))
