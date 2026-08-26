"""Append-only session event log: the durable source of conversation history.

Every model-visible fact is appended here; provider request history is
derived from this log (see ``app.core.session_surface``). Events are never
updated or deleted - corrections happen as new events that shadow old ones.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_event import SessionEvent

# Event types that participate in the model-visible surface.
USER_MESSAGE = "user/message"
ASSISTANT_MESSAGE = "assistant/message"
TOOL_CALL = "tool/call"
TOOL_RESULT = "tool/result"
COMPACTION_SUMMARY = "compaction/summary"

_ALLOWED_TYPES = {
    USER_MESSAGE,
    ASSISTANT_MESSAGE,
    TOOL_CALL,
    TOOL_RESULT,
    COMPACTION_SUMMARY,
}


class SessionEventError(ValueError):
    """An event payload violates the append contract."""


def _assert_lossless_json(value: Any, path: str = "data") -> None:
    """Reject payloads JSON cannot round-trip losslessly.

    Mirrors dsh's snapshotJsonValue discipline: a bad event must fail at the
    append site, never at read/derive time.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise SessionEventError(f"{path}: object keys must be strings")
            _assert_lossless_json(v, f"{path}.{k}")
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            _assert_lossless_json(v, f"{path}[{i}]")
        return
    raise SessionEventError(f"{path}: type {type(value).__name__} is not losslessly serializable")


def validate_event_payload(type_: str, data: dict[str, Any]) -> None:
    """Validate an event before append - cheap structural checks only."""
    if type_ not in _ALLOWED_TYPES:
        raise SessionEventError(f"unknown session event type '{type_}'")
    _assert_lossless_json(data)
    # Surface ops must be well-formed so derive_messages can trust them.
    surface_op = data.get("surface_op", "append")
    if surface_op == "append":
        return
    if not isinstance(surface_op, dict) or surface_op.get("op") != "replace":
        raise SessionEventError("surface_op must be 'append' or {op: 'replace', start_seq, end_seq}")
    start_seq = surface_op.get("start_seq")
    end_seq = surface_op.get("end_seq")
    if not isinstance(start_seq, int) or not isinstance(end_seq, int):
        raise SessionEventError("replace surface_op needs integer start_seq/end_seq")
    source_seqs = data.get("source_seqs")
    if not isinstance(source_seqs, list) or not source_seqs:
        raise SessionEventError("replace events must cite the shadowed source_seqs")


async def next_seq(db: AsyncSession, session_id: str) -> int:
    # populate_existing defeats the identity-map cache: after a flush inside
    # this transaction, a cached stale row must not shadow the MAX value the
    # database actually holds.
    res = await db.execute(
        select(func.max(SessionEvent.seq))
        .where(SessionEvent.session_id == session_id)
        .execution_options(populate_existing=True)
    )
    current = res.scalar()
    # NOTE: not `current or -1` - seq 0 is valid and falsy.
    return 0 if current is None else current + 1


async def append_event(
    db: AsyncSession,
    *,
    session_id: str,
    org_id: str,
    type_: str,
    data: dict[str, Any],
) -> int:
    """Append one event and return its seq.

    Pending changes are flushed first so MAX(seq) sees every event appended
    in this transaction (autoflush timing differs across drivers). The unique
    (session_id, seq) index is the hard contiguity guarantee - a concurrent
    writer collision surfaces as an IntegrityError on commit instead of
    silently forking the log.
    """
    validate_event_payload(type_, data)
    await db.flush()
    seq = await next_seq(db, session_id)
    db.add(
        SessionEvent(
            org_id=org_id,
            session_id=session_id,
            seq=seq,
            type=type_,
            data=data,
        )
    )
    await db.flush()
    return seq


async def load_events(
    db: AsyncSession,
    session_id: str,
    *,
    after_seq: int = -1,
) -> list[SessionEvent]:
    res = await db.execute(
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id, SessionEvent.seq > after_seq)
        .order_by(SessionEvent.seq)
    )
    return list(res.scalars().all())


def assert_contiguous(events: list[SessionEvent]) -> None:
    """Fail loudly on gaps - silent tolerance would gut the session."""
    for expected, ev in enumerate(events):
        if ev.seq != expected:
            raise SessionEventError(
                f"session event log gap: expected seq {expected}, found {ev.seq}"
            )


def event_dict(ev: SessionEvent) -> dict[str, Any]:
    return {"seq": ev.seq, "type": ev.type, "data": ev.data}


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
