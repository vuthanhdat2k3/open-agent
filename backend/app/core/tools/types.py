from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tools.risk_tier import RiskTier


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
    org_id: str | None = None
    user_id: str | None = None
    current_task_id: str | None = None
    root_run_id: str | None = None
    model_id: str | None = None
    timezone_name: str = "UTC"
    actor_agent_identity_id: str | None = None
    delegation_chain: list | dict | None = None
    # Optional async callback for streaming incremental progress (e.g. stdout
    # lines from sandbox tools) back to the caller. Tools that support it
    # await ctx.emit({"event": ..., "data": ...}); callers that do not set it
    # must still work, so every call site guards with `if ctx.emit:`.
    emit: Callable[..., Awaitable[None]] | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON schema (dict)
    run: Callable[[dict[str, Any], ToolContext], Awaitable[str]]

    risk_tier: RiskTier = RiskTier.safe
    requires_approval: bool = False
    timeout_s: float = 30.0
    max_retries: int = 0


def tool_to_openai_schema(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.input_schema,
        },
    }
