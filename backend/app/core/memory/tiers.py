from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMClient, resolve_api_key
from app.models.memory import AgentMemory, SessionMemory
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider


async def compact_tiered_memory(
    session_id: str,
    db: AsyncSession,
    agent_model: Model,
    provider: Provider,
    hot_window: int = 6,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Hierarchical memory management (Hot / Warm / Cold tiering).

    - Hot Tier: Last N verbatim messages.
    - Warm Tier: Rolling conversation summary persisted in SessionMemory.
    - Cold Tier: Semantic facts and user profile entries retrieved from AgentMemory.

    Returns structured tiered context components.
    """
    # 1. Fetch Hot Tier messages
    res_msg = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.position)
    )
    messages = list(res_msg.scalars().all())

    if len(messages) <= hot_window:
        hot_text = "\n\n".join(f"{m.role}: {m.content}" for m in messages)
        return {
            "hot": hot_text,
            "warm": "",
            "cold": "",
            "combined": hot_text,
        }

    hot_messages = messages[-hot_window:]
    older_messages = messages[:-hot_window]

    hot_text = "\n\n".join(f"{m.role}: {m.content}" for m in hot_messages)
    older_transcript = "\n\n".join(f"{m.role}: {m.content}" for m in older_messages)

    # 2. Warm Tier: Summarize older transcript
    warm_summary = ""
    try:
        llm = LLMClient(provider.base_url, resolve_api_key(provider), agent_model.name)
        summary_text, _, _ = await llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Summarize the conversation excerpt into concise facts, "
                        "decisions, and open questions for continuation. Be terse."
                    ),
                },
                {"role": "user", "content": older_transcript},
            ],
            temperature=0.2,
        )
        warm_summary = summary_text.strip()
    except Exception:  # noqa: BLE001
        warm_summary = older_transcript

    # Persist Warm summary to SessionMemory
    res_mem = await db.execute(
        select(SessionMemory).where(
            SessionMemory.session_id == session_id,
            SessionMemory.key == "warm_summary",
        )
    )
    smem = res_mem.scalar_one_or_none()
    if smem:
        smem.value = warm_summary
    else:
        smem = SessionMemory(
            session_id=session_id,
            key="warm_summary",
            value=warm_summary,
        )
        db.add(smem)
    await db.flush()

    # 3. Cold Tier: Extract agent memory facts if agent_id is present
    cold_facts = []
    if agent_id:
        res_agent_mem = await db.execute(
            select(AgentMemory).where(AgentMemory.agent_id == agent_id).limit(10)
        )
        cold_facts = [
            f"{mem.memory_type}.{mem.attribute}: {mem.value}"
            for mem in res_agent_mem.scalars().all()
        ]

    cold_text = "\n".join(cold_facts) if cold_facts else ""

    parts = []
    if cold_text:
        parts.append(f"[Cold Memory / User Profile]\n{cold_text}")
    if warm_summary:
        parts.append(f"[Warm Memory / Session Summary]\n{warm_summary}")
    parts.append(f"[Hot Memory / Recent Turn]\n{hot_text}")

    combined = "\n\n".join(parts)

    return {
        "hot": hot_text,
        "warm": warm_summary,
        "cold": cold_text,
        "combined": combined,
    }
