from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
from sqlalchemy import select

from app.core.tools.registry import register
from app.core.tools.types import ToolContext, ToolSpec
from app.models.memory import AgentMemory
from app.core.memory_schema import (
    DEFAULT_OWNER_TYPE,
    MemorySchemaError,
    normalize,
    to_metadata_dict,
)


async def _save_memory(args: dict[str, Any], ctx: ToolContext) -> str:
    if not ctx.db or not ctx.agent_id:
        return "error: memory requires a database-backed agent context"

    try:
        norm = normalize(
            memory_type=args.get("memory_type"),
            attribute=args.get("attribute"),
            value=args.get("value", ""),
            importance=args.get("importance"),
            confidence=args.get("confidence"),
            source=args.get("source"),
        )
    except MemorySchemaError as e:
        return f"error: {e}"

    meta = to_metadata_dict(
        args.get("conversation_id"), args.get("message_id")
    )

    db = ctx.db
    res = await db.execute(
        select(AgentMemory).where(
            AgentMemory.agent_id == ctx.agent_id,
            AgentMemory.memory_type == norm.memory_type,
            AgentMemory.attribute == norm.attribute,
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        # UPSERT: update in place, never create a second row.
        existing.value = norm.value
        existing.importance = norm.importance
        existing.confidence = norm.confidence
        existing.source = norm.source
        if meta:
            existing.meta = meta
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            AgentMemory(
                agent_id=ctx.agent_id,
                owner_type=DEFAULT_OWNER_TYPE,
                memory_type=norm.memory_type,
                attribute=norm.attribute,
                value=norm.value,
                importance=norm.importance,
                confidence=norm.confidence,
                source=norm.source,
                meta=meta,
            )
        )
    await db.commit()
    return f"remembered: {norm.memory_type}.{norm.attribute} = {norm.value}"


async def _call_memory(args: dict[str, Any], ctx: ToolContext) -> str:
    if not ctx.db or not ctx.agent_id:
        return "(no user memory available in this context)"

    db = ctx.db
    memory_type = (args.get("memory_type") or "").strip().lower() or None
    attribute = (args.get("attribute") or "").strip().lower() or None
    query = (args.get("query") or "").strip().lower() or None

    stmt = select(AgentMemory).where(AgentMemory.agent_id == ctx.agent_id)
    if memory_type:
        stmt = stmt.where(AgentMemory.memory_type == memory_type)
    if attribute:
        stmt = stmt.where(AgentMemory.attribute == attribute)
    stmt = stmt.order_by(AgentMemory.importance.desc(), AgentMemory.updated_at.desc())
    res = await db.execute(stmt)
    memories = res.scalars().all()

    # Mark accessed for future retrieval ranking.
    now = datetime.now(timezone.utc)
    for m in memories:
        m.last_accessed_at = now

    if not memories:
        if memory_type:
            return f"(no memory found for type '{memory_type}')"
        if attribute:
            return f"(no memory found for attribute '{attribute}')"
        return "(no user memory stored yet)"

    if query:
        matches = [
            m
            for m in memories
            if query in m.attribute.lower() or query in m.value.lower()
        ]
        if not matches:
            return f"no memory found for '{query}'"
        memories = matches

    if memory_type or attribute:
        # Scoped query: return flat lines.
        await db.commit()
        return "\n".join(f"{m.attribute}: {m.value}" for m in memories)

    # No filter: return grouped summary so the model isn't drowned in rows.
    grouped: dict[str, list[str]] = {}
    for m in memories:
        grouped.setdefault(m.memory_type, []).append(f"{m.attribute}: {m.value}")
    await db.commit()
    return "\n".join(
        f"{mtype}:\n" + "\n".join(f"  {line}" for line in lines)
        for mtype, lines in grouped.items()
    )


register(
    ToolSpec(
        name="save_memory",
        description=(
            "Persist a structured fact about the user. Provide 'memory_type' "
            "(profile|preference|project|goal|skill|relationship|history|fact) "
            "and 'attribute' (e.g. 'name', 'language'). Common aliases "
            "(full_name, formal_name, display_name, username) are auto-folded "
            "into the canonical attribute, and writes UPSERT (update, never "
            "duplicate). Optional: importance, confidence (1.0 if user stated, "
            "<1.0 if inferred), source, conversation_id, message_id."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "memory_type": {
                    "type": "string",
                    "description": "One of: profile, preference, project, goal, skill, relationship, history, fact",
                },
                "attribute": {
                    "type": "string",
                    "description": "Canonical attribute, e.g. 'name', 'language', 'editor'. Aliases are normalized.",
                },
                "value": {
                    "type": "string",
                    "description": "The fact to remember, e.g. 'Đạt', 'Vietnamese'",
                },
                "importance": {
                    "type": "integer",
                    "description": "Retrieval priority (default 5; profile.name defaults to 10)",
                },
                "confidence": {
                    "type": "number",
                    "description": "1.0 if user stated, lower if inferred",
                },
                "source": {
                    "type": "string",
                    "description": "user | agent | imported | system (default agent)",
                },
            },
            "required": ["memory_type", "attribute", "value"],
        },
        run=_save_memory,
    )
)


register(
    ToolSpec(
        name="call_memory",
        description=(
            "Recall structured user facts. Scope with 'memory_type' (returns "
            "that type's attributes) or 'attribute' (returns that attribute), "
            "or 'query' (keyword filter). With no filter, returns a grouped "
            "summary by type — not a raw dump of every row."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "memory_type": {
                    "type": "string",
                    "description": "Filter by type, e.g. 'profile'",
                },
                "attribute": {
                    "type": "string",
                    "description": "Filter by attribute, e.g. 'name'",
                },
                "query": {
                    "type": "string",
                    "description": "Keyword to search across attributes/values",
                },
            },
            "required": [],
        },
        run=_call_memory,
    )
)
