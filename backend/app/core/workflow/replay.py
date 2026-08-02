"""Deterministic replay of a recorded run.

Debugging an agent is otherwise guesswork: the same prompt can take a
different path on every attempt. Recording each tool result lets a run be
re-executed against the recording, so the investigated behaviour is the one
that actually happened — and no tool fires a second time.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.guardrails.secrets import scan_and_redact
from app.models.tool_call_record import ToolCallRecord


class ReplayDiverged(RuntimeError):
    """The replayed run asked for something the recording does not contain.

    Raised instead of silently falling back to live execution: a replay that
    quietly starts calling real tools costs money and causes side effects the
    operator never asked for.
    """

    def __init__(self, *, sequence: int, expected: str | None, requested: str) -> None:
        super().__init__(
            f"replay diverged at call #{sequence}: recording has "
            f"{expected or 'no further calls'}, run requested {requested}"
        )
        self.sequence = sequence
        self.expected = expected
        self.requested = requested


def arguments_hash(arguments: dict) -> str:
    """Stable hash of tool arguments, insensitive to key order."""
    canonical = json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def record_tool_call(
    db: AsyncSession,
    *,
    org_id: str,
    sequence: int,
    tool_name: str,
    arguments: dict,
    result: str,
    status: str = "ok",
    duration_ms: int = 0,
    session_id: str | None = None,
    workflow_run_id: str | None = None,
    node_run_id: str | None = None,
    commit: bool = False,
) -> ToolCallRecord:
    """Store one tool result for later replay.

    The result is redacted first — a replay store full of live credentials
    would undo the guardrail that scrubbed them from the transcript.
    """
    safe_result, _ = scan_and_redact(str(result))
    record = ToolCallRecord(
        org_id=org_id,
        workflow_run_id=workflow_run_id,
        node_run_id=node_run_id,
        session_id=session_id,
        sequence=sequence,
        tool_name=tool_name,
        arguments_hash=arguments_hash(arguments),
        arguments=arguments or {},
        result=safe_result,
        status=status,
        duration_ms=duration_ms,
    )
    db.add(record)
    if commit:
        await db.commit()
    return record


class ReplayCursor:
    """Serves recorded tool results in order for a replayed run."""

    def __init__(self, records: list[ToolCallRecord]) -> None:
        self._records = sorted(records, key=lambda r: r.sequence)
        self._position = 0

    @classmethod
    async def load(
        cls,
        db: AsyncSession,
        *,
        org_id: str,
        session_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> ReplayCursor:
        stmt = select(ToolCallRecord).where(ToolCallRecord.org_id == org_id)
        if workflow_run_id:
            stmt = stmt.where(ToolCallRecord.workflow_run_id == workflow_run_id)
        else:
            stmt = stmt.where(ToolCallRecord.session_id == session_id)
        res = await db.execute(stmt.order_by(ToolCallRecord.sequence))
        return cls(list(res.scalars().all()))

    def __len__(self) -> int:
        return len(self._records)

    @property
    def exhausted(self) -> bool:
        return self._position >= len(self._records)

    def next_result(self, tool_name: str, arguments: dict) -> str:
        """Return the recorded result for the next call.

        Raises :class:`ReplayDiverged` when the run takes a different path
        than the recording — the model asked for another tool, passed
        different arguments, or made more calls than were recorded.
        """
        if self.exhausted:
            raise ReplayDiverged(sequence=self._position, expected=None, requested=tool_name)

        record = self._records[self._position]
        if record.tool_name != tool_name:
            raise ReplayDiverged(
                sequence=record.sequence, expected=record.tool_name, requested=tool_name
            )
        if record.arguments_hash != arguments_hash(arguments):
            raise ReplayDiverged(
                sequence=record.sequence,
                expected=f"{record.tool_name} with different arguments",
                requested=f"{tool_name} {arguments_hash(arguments)[:12]}",
            )

        self._position += 1
        return record.result
