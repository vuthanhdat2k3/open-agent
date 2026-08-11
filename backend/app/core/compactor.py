from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.factory import build_driver
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider


async def compact_session(
    session_id: str,
    db: AsyncSession,
    agent_model: Model,
    provider: Provider,
    keep_last: int = 4,
) -> str:
    """Load a session's messages, summarize the older ones, return a compacted
    context string combining the summary + recent messages."""
    res = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.position)
    )
    messages = res.scalars().all()
    if len(messages) <= keep_last:
        return "\n\n".join(f"{m.role}: {m.content}" for m in messages)

    recent = messages[-keep_last:]
    to_summarize = messages[:-keep_last]
    transcript = "\n\n".join(f"{m.role}: {m.content}" for m in to_summarize)
    try:
        llm = build_driver(provider, agent_model)
        summary, _, _ = await llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Summarize the conversation excerpt into concise facts, "
                        "decisions, and open questions for continuation. Be terse."
                    ),
                },
                {"role": "user", "content": transcript},
            ],
            temperature=0.2,
        )
    except Exception:  # noqa: BLE001
        summary = transcript

    recent_text = "\n\n".join(f"{m.role}: {m.content}" for m in recent)
    return f"[Summary of earlier conversation]\n{summary}\n\n[Recent]\n{recent_text}"
