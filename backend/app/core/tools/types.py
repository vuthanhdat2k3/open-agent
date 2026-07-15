from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    """Ambient dependencies handed to every tool at execution time."""

    db: AsyncSession
    depth: int = 0
    workspace_dir: str = "./workspace"
    # set by the workflow/agent runtime when MCP tools are present
    mcp_manager: Any | None = None
    agent_id: str | None = None
    session_id: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON schema (dict)
    run: Callable[[dict[str, Any], ToolContext], Awaitable[str]]


def tool_to_openai_schema(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.input_schema,
        },
    }
