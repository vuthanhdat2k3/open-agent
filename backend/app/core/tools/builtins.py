from typing import Any

import httpx

from app.config import get_settings

# Register the additional builtin tools (filesystem, shell, web search).
# Importing this module triggers their registration as a side effect.
from app.core.tools import (
    filesystem,  # noqa: F401
    memory,  # noqa: F401
    shell,  # noqa: F401
    web_search,  # noqa: F401
)
from app.core.tools.paths import safe_resolve
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec

settings = get_settings()

# Fallback in-memory dictionary for testing/non-DB contexts
MEMORY: dict[str, str] = {}

MAX_ATTACHMENT_CHARS = 50_000


async def _read_attachment(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path", "")
    if not path:
        return "error: missing 'path'"
    target = safe_resolve(ctx.workspace_dir, path)
    if target is None:
        return "error: path escapes workspace directory"
    if not target.is_file():
        return f"error: file not found: {path}"
    try:
        with open(target, encoding="utf-8", errors="replace") as f:
            data = f.read(MAX_ATTACHMENT_CHARS)
    except Exception as e:  # noqa: BLE001
        return f"error reading file: {e}"
    if len(data) == MAX_ATTACHMENT_CHARS:
        data += "\n...[truncated]"
    return data


async def _web_fetch(args: dict[str, Any], ctx: ToolContext) -> str:
    url = args.get("url", "")
    if not url:
        return "error: missing 'url'"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "OpenAgent/0.1"})
        text = resp.text
    except Exception as e:  # noqa: BLE001
        return f"error fetching url: {e}"
    if len(text) > MAX_ATTACHMENT_CHARS:
        text = text[:MAX_ATTACHMENT_CHARS] + "\n...[truncated]"
    return text


async def _memory_store(args: dict[str, Any], ctx: ToolContext) -> str:
    key = args.get("key")
    value = args.get("value", "")
    if not key:
        return "error: missing 'key'"
    if not ctx.db or not ctx.session_id:
        MEMORY[key] = str(value)
        return f"stored key '{key}'"

    from sqlalchemy import select

    from app.models.memory import SessionMemory

    db = ctx.db
    res = await db.execute(
        select(SessionMemory).where(
            SessionMemory.session_id == ctx.session_id, SessionMemory.key == key
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        existing.value = str(value)
    else:
        org_id = ctx.org_id
        if not org_id and ctx.session_id:
            from app.models.session import Session

            res_sess = await db.execute(select(Session.org_id).where(Session.id == ctx.session_id))
            org_id = res_sess.scalar_one_or_none()
        if not org_id:
            org_id = "default-org-id"

        db.add(
            SessionMemory(
                org_id=org_id,
                created_by_user_id=ctx.user_id,
                session_id=ctx.session_id,
                key=key,
                value=str(value),
            )
        )
    await db.commit()
    return f"stored key '{key}'"


async def _memory_recall(args: dict[str, Any], ctx: ToolContext) -> str:
    key = args.get("key")
    if not key:
        return "error: missing 'key'"
    if not ctx.db or not ctx.session_id:
        return MEMORY.get(key, "not found")

    from sqlalchemy import select

    from app.models.memory import SessionMemory

    db = ctx.db
    res = await db.execute(
        select(SessionMemory).where(
            SessionMemory.session_id == ctx.session_id, SessionMemory.key == key
        )
    )
    existing = res.scalar_one_or_none()
    if not existing:
        return "not found"
    return existing.value


async def _call_agent(args: dict[str, Any], ctx: ToolContext) -> str:
    target_agent_id = args.get("target_agent_id") or args.get("agent_id")
    instruction = args.get("instruction") or args.get("message") or ""
    if not target_agent_id:
        return "error: missing 'target_agent_id'"
    if not instruction:
        return "error: missing 'instruction'"
    from app.config import get_settings

    if ctx.depth >= get_settings().max_agent_depth:
        return f"error: max agent depth ({get_settings().max_agent_depth}) exceeded"
    # Lazy import to avoid circular dependency with agent_loop.
    from sqlalchemy import select

    from app.core.agent_loop import run_agent_loop
    from app.db.base import utc_now
    from app.models.agent import Agent
    from app.models.task import Task

    result = await ctx.db.execute(
        select(Agent).where(Agent.id == target_agent_id, Agent.org_id == ctx.org_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        return f"error: agent '{target_agent_id}' not found"

    task = Task(
        org_id=agent.org_id,
        parent_task_id=ctx.current_task_id,
        root_run_id=ctx.root_run_id or ctx.session_id or ctx.current_task_id or agent.id,
        agent_id=agent.id,
        goal=instruction,
        status="running",
        depth=ctx.depth + 1,
        started_at=utc_now(),
    )
    ctx.db.add(task)
    await ctx.db.commit()
    await ctx.db.refresh(task)

    try:
        loop_result = await run_agent_loop(
            agent,
            instruction,
            ctx.db,
            depth=ctx.depth + 1,
            current_task_id=task.id,
            root_run_id=task.root_run_id,
        )
    except Exception as exc:  # noqa: BLE001
        task.status = "failed"
        task.result = str(exc)
        task.finished_at = utc_now()
        await ctx.db.commit()
        return f"error: subagent failed: {exc}"

    task.status = "succeeded"
    task.result = loop_result.content
    task.token_usage = loop_result.usage
    task.finished_at = utc_now()
    await ctx.db.commit()
    return loop_result.content


register(
    ToolSpec(
        name="read_attachment",
        description="Read a text file from the workspace. Provide a relative 'path'.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside workspace"}
            },
            "required": ["path"],
        },
        run=_read_attachment,
        risk_tier=RiskTier.read,
    )
)

register(
    ToolSpec(
        name="web_fetch",
        description="Fetch a URL and return its text content.",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full URL to fetch"}},
            "required": ["url"],
        },
        run=_web_fetch,
        risk_tier=RiskTier.read,
    )
)

register(
    ToolSpec(
        name="memory_store",
        description="Store a value under a key in the agent memory.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
        run=_memory_store,
        risk_tier=RiskTier.safe,
    )
)

register(
    ToolSpec(
        name="memory_recall",
        description="Recall a previously stored value by key.",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
        run=_memory_recall,
        risk_tier=RiskTier.safe,
    )
)

register(
    ToolSpec(
        name="call_agent",
        description=(
            "Delegate a task to another configured agent by id. Returns that agent's final answer."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string"},
                "instruction": {"type": "string"},
            },
            "required": ["target_agent_id", "instruction"],
        },
        run=_call_agent,
        risk_tier=RiskTier.execute,
    )
)
