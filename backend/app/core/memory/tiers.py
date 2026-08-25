from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMClient  # noqa: F401
from app.core.observability.llm_trace import ObservabilityContext
from app.core.providers.factory import build_driver
from app.models.memory import AgentMemory, SessionMemory
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider

# Retry policy for the summarizer: transient provider failures get a second
# chance, but a context-overflow error will not be fixed by retrying the same
# oversized input.
_SUMMARIZE_MAX_ATTEMPTS = 3
_FALLBACK_TAIL_CHARS = 6000

WARM_SUMMARY_KEY = "warm_summary"
WARM_SUMMARY_UPTO_KEY = "warm_summary_upto"


def _is_context_overflow(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "context length",
        "context_length",
        "maximum context",
        "too many tokens",
        "max_tokens",
        "reduce the length",
    )
    return any(marker in text for marker in markers)


def _truncate_tail(messages: list[Message], max_chars: int) -> str:
    """Render the newest messages that fit into max_chars, oldest-trimmed.

    This is the safe fallback when summarization fails entirely: it keeps
    bounded, recent context instead of re-injecting the full transcript —
    which is exactly what overloaded the window in the first place.
    """
    lines = [f"{m.role}: {m.content}" for m in messages]
    kept: list[str] = []
    total = 0
    for line in reversed(lines):
        if total + len(line) > max_chars and kept:
            break
        kept.append(line)
        total += len(line)
    kept.reverse()
    return "\n\n".join(kept)


async def _summarize(
    provider: Provider,
    model: Model,
    prompt_user: str,
    *,
    observability: ObservabilityContext | None,
    generation_name: str,
) -> str:
    """Call the summarizer with bounded retries; raises after exhaustion."""
    llm = build_driver(
        provider,
        model,
        observability=observability,
        generation_name=generation_name,
    )
    last_exc: Exception | None = None
    for _attempt in range(_SUMMARIZE_MAX_ATTEMPTS):
        try:
            summary, _, _ = await llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Summarize the conversation excerpt into concise facts, "
                            "decisions, and open questions for continuation. Be terse."
                        ),
                    },
                    {"role": "user", "content": prompt_user},
                ],
                temperature=0.2,
            )
            summary_text = summary.strip()
            if not summary_text:
                raise RuntimeError("summarizer returned an empty summary")
            return summary_text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_context_overflow(exc):
                raise
    raise last_exc  # type: ignore[misc]


async def _load_session_memory(session_id: str, key: str, db: AsyncSession) -> SessionMemory | None:
    res = await db.execute(
        select(SessionMemory).where(
            SessionMemory.session_id == session_id,
            SessionMemory.key == key,
        )
    )
    return res.scalar_one_or_none()


def _parse_upto(value: str | None, positions: list[int]) -> int | None:
    """Return the stored summarization cursor when it still points at an
    existing message position; otherwise None (full re-summarize)."""
    if value is None or not value.isdigit():
        return None
    upto = int(value)
    if upto in positions:
        return upto
    return None


async def compact_tiered_memory(
    session_id: str,
    db: AsyncSession,
    agent_model: Model,
    provider: Provider,
    hot_window: int = 6,
    agent_id: str | None = None,
    org_id: str | None = None,
    created_by_user_id: str | None = None,
    *,
    observability: ObservabilityContext | None = None,
) -> dict[str, Any]:
    """Hierarchical memory management (Hot / Warm / Cold tiering).

    - Hot Tier: Last N verbatim messages.
    - Warm Tier: Rolling conversation summary persisted in SessionMemory.
      Incremental: only new messages since the previous summary are sent to
      the summarizer, merged with the prior summary.
    - Cold Tier: Top structured facts and user profile entries retrieved from AgentMemory (ordered by importance).

    Returns structured tiered context components.
    """
    # 1. Fetch Hot Tier messages
    res_msg = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.position)
    )
    messages = list(res_msg.scalars().all())

    # Resolve org_id / created_by_user_id if not provided
    if not org_id or not created_by_user_id:
        from app.models.session import Session

        res_sess = await db.execute(select(Session).where(Session.id == session_id))
        sess = res_sess.scalar_one_or_none()
        if sess:
            org_id = org_id or sess.org_id
            created_by_user_id = created_by_user_id or sess.created_by_user_id

    if not org_id and messages:
        org_id = messages[0].org_id
        created_by_user_id = created_by_user_id or messages[0].created_by_user_id

    if not org_id:
        raise ValueError("org_id is required for tiered memory persistence")

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

    # 2. Warm Tier: incremental rolling summary.
    prev_summary_row = await _load_session_memory(session_id, WARM_SUMMARY_KEY, db)
    upto_row = await _load_session_memory(session_id, WARM_SUMMARY_UPTO_KEY, db)
    prev_summary = (prev_summary_row.value or "").strip() if prev_summary_row else ""
    prev_upto = (
        _parse_upto(upto_row.value if upto_row else None, [m.position for m in messages])
        if prev_summary
        else None
    )

    if prev_summary and prev_upto is not None:
        # Incremental path: summarize only what is newer than the cursor and
        # merge it into the existing summary.
        new_messages = [m for m in older_messages if m.position > prev_upto]
        if not new_messages:
            warm_summary = prev_summary
            summarized_through = prev_upto
        else:
            new_transcript = "\n\n".join(f"{m.role}: {m.content}" for m in new_messages)
            try:
                warm_summary = await _summarize(
                    provider,
                    agent_model,
                    (
                        "Previous summary of this conversation:\n\n"
                        f"{prev_summary}\n\n"
                        "New messages since that summary:\n\n"
                        f"{new_transcript}\n\n"
                        "Merge the new messages into the summary so it stays "
                        "concise, complete, and up to date."
                    ),
                    observability=observability,
                    generation_name="memory-summarization",
                )
                summarized_through = new_messages[-1].position
            except Exception:  # noqa: BLE001
                # Keep the durable previous summary plus a bounded tail of the
                # unsummarized messages - never the full raw transcript.
                warm_summary = (
                    f"{prev_summary}\n\n"
                    "[Unsummarized recent messages — truncated]\n"
                    + _truncate_tail(new_messages, _FALLBACK_TAIL_CHARS)
                )
                summarized_through = prev_upto
    else:
        # Full path (first run, or legacy rows without a valid cursor).
        older_transcript = "\n\n".join(f"{m.role}: {m.content}" for m in older_messages)
        try:
            warm_summary = await _summarize(
                provider,
                agent_model,
                older_transcript,
                observability=observability,
                generation_name="memory-summarization",
            )
            summarized_through = older_messages[-1].position
        except Exception:  # noqa: BLE001
            warm_summary = (
                "[Unsummarized earlier conversation — truncated]\n"
                + _truncate_tail(older_messages, _FALLBACK_TAIL_CHARS)
            )
            summarized_through = None

    # Persist Warm summary to SessionMemory alongside the summarization
    # cursor that enables the incremental path next time.
    smem = prev_summary_row
    if smem:
        smem.value = warm_summary
        if created_by_user_id:
            smem.created_by_user_id = created_by_user_id
    else:
        smem = SessionMemory(
            session_id=session_id,
            org_id=org_id,
            created_by_user_id=created_by_user_id,
            key=WARM_SUMMARY_KEY,
            value=warm_summary,
        )
        db.add(smem)

    upto_value = str(summarized_through) if summarized_through is not None else ""
    if upto_row:
        upto_row.value = upto_value
    else:
        db.add(
            SessionMemory(
                session_id=session_id,
                org_id=org_id,
                created_by_user_id=created_by_user_id,
                key=WARM_SUMMARY_UPTO_KEY,
                value=upto_value,
            )
        )
    await db.flush()

    # 3. Cold Tier: Extract top structured agent memory facts if agent_id is present
    cold_facts = []
    if agent_id:
        res_agent_mem = await db.execute(
            select(AgentMemory)
            .where(AgentMemory.agent_id == agent_id)
            .order_by(AgentMemory.importance.desc(), AgentMemory.updated_at.desc())
            .limit(10)
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
