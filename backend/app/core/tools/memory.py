from __future__ import annotations

from typing import Any
from sqlalchemy import select

from app.core.tools.registry import register
from app.core.tools.types import ToolContext, ToolSpec
from app.models.memory import AgentMemory

# Fallback in-memory dictionary for testing/non-DB contexts
USER_MEMORY: dict[str, str] = {}


async def _save_memory(args: dict[str, Any], ctx: ToolContext) -> str:
    key = args.get("key")
    value = args.get("value", "")
    if not key:
        return "error: missing 'key'"
    if not ctx.db or not ctx.agent_id:
        USER_MEMORY[key] = str(value)
        return f"remembered: {key} = {value}"

    db = ctx.db
    res = await db.execute(
        select(AgentMemory).where(
            AgentMemory.agent_id == ctx.agent_id,
            AgentMemory.key == key
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        existing.value = str(value)
    else:
        db.add(AgentMemory(agent_id=ctx.agent_id, key=key, value=str(value)))
    await db.commit()
    return f"remembered: {key} = {value}"


async def _call_memory(args: dict[str, Any], ctx: ToolContext) -> str:
    query = (args.get("query") or args.get("key") or "").strip().lower()
    if not ctx.db or not ctx.agent_id:
        if not query:
            if not USER_MEMORY:
                return "(no user memory stored yet)"
            return "\n".join(f"{k}: {v}" for k, v in USER_MEMORY.items())
        matches = {
            k: v
            for k, v in USER_MEMORY.items()
            if query in k.lower() or query in v.lower()
        }
        if not matches:
            return f"no memory found for '{query}'"
        return "\n".join(f"{k}: {v}" for k, v in matches.items())

    db = ctx.db
    res = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_id == ctx.agent_id)
    )
    memories = res.scalars().all()

    if not query:
        if not memories:
            return "(no user memory stored yet)"
        return "\n".join(f"{m.key}: {m.value}" for m in memories)

    matches = [
        m for m in memories
        if query in m.key.lower() or query in m.value.lower()
    ]
    if not matches:
        return f"no memory found for '{query}'"
    return "\n".join(f"{m.key}: {m.value}" for m in matches)


register(
    ToolSpec(
        name="save_memory",
        description=(
            "Save a fact about the user (name, preferences, context, goals) so it "
            "survives across turns. Provide a short 'key' (e.g. 'name', "
            "'preferred_language') and its 'value'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Short label for the fact, e.g. 'name', 'preferred_language'",
                },
                "value": {
                    "type": "string",
                    "description": "The fact to remember, e.g. 'Dat', 'Python'",
                },
            },
            "required": ["key", "value"],
        },
        run=_save_memory,
    )
)

register(
    ToolSpec(
        name="call_memory",
        description=(
            "Recall stored user facts. Optional 'query' (or 'key') filters by "
            "keyword; omit it to list everything remembered about the user."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to search stored user facts (optional)",
                },
                "key": {
                    "type": "string",
                    "description": "Exact key to look up (optional, used if query omitted)",
                },
            },
            "required": [],
        },
        run=_call_memory,
    )
)
