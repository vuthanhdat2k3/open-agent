"""Durable event log for chat runs.

The agent loop already *emits* SSE-shaped events (token, reasoning,
tool_call, ...) but since the "durable chat workflow" change the run happens
in a background task / worker, so nothing consumed them. This module makes
the stream durable: every emitted event is appended to ``chat_run_events``
and mirrored into a small ``tasks.progress`` checkpoint.

A client that reloads the page mid-run can then
``GET /api/chat/runs/{id}/events`` to drain everything it missed (rebuilding
partial text, reasoning and running tool cards) and follow new events live
until the run reaches a terminal state.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import gen_id, utc_now
from app.db.session import SessionLocal
from app.models.chat_run_event import ChatRunEvent
from app.models.task import Task

# Terminal events that (together with the Task status) tell a follower it can
# stop watching. ``error`` is terminal unless the loop retries internally —
# the loop only emits ``error`` when the run is actually over.
TERMINAL_EVENTS = {"message_done", "error", "approval_required", "approval_rejected", "replay_diverged"}

# How long a chat task may go without emitting an event or a progress
# heartbeat before it counts as orphaned (worker crashed mid-run).
CHAT_ORPHAN_STALE_SECONDS = 120

# Progress heartbeats are cheap but not free; don't write more often than
# this while tokens stream in.
_PROGRESS_MIN_INTERVAL = 1.0
# A chat run's tokens are only visible to the browser once they are in this
# log, so the buffer window is the floor on perceived streaming latency. Keep
# it near one animation frame: long enough to batch a multi-row insert instead
# of one round-trip per token, short enough that text still appears token by
# token rather than in phrase-sized jumps. The size cap is a safety valve for
# providers that burst faster than the timer.
_EVENT_BATCH_SIZE = 8
_EVENT_BATCH_DELAY = 0.025
_LIVENESS_INTERVAL = 15.0


class ChatEventRecorder:
    """Append events for one chat run; yield them through unchanged.

    Every write goes through ``SessionLocal`` (its own short transaction), so
    recording works identically in the inline API process and in the arq
    worker, and never entangles the request-scoped session the agent loop
    commits on.
    """

    def __init__(self, org_id: str, run_id: str, session_id: str | None = None):
        self.org_id = org_id
        self.run_id = run_id
        self.session_id = session_id
        self.seq = 0
        self._pending: list[ChatRunEvent] = []
        self._flush_task: asyncio.Task | None = None
        self._flush_lock = asyncio.Lock()
        self._liveness_task: asyncio.Task | None = None
        self._phase = "queued"
        self._last_progress_at = 0.0

    def start_liveness(self) -> None:
        """Keep a live run fresh while the provider emits no token events."""
        if self._liveness_task is None or self._liveness_task.done():
            self._liveness_task = asyncio.create_task(self._liveness_loop())

    async def _liveness_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(_LIVENESS_INTERVAL)
                await self.flush_progress(phase=self._phase)
        except asyncio.CancelledError:
            raise

    async def record(self, ev: dict[str, Any]) -> dict[str, Any]:
        """Append ``ev`` to the log asynchronously; returns ``ev`` unchanged.

        Failures are swallowed into the log — losing an event row (streaming
        degrades to the old wait-until-done behavior) is always preferable to
        failing the user's run.
        """
        self.seq += 1
        seq = self.seq
        event = str(ev.get("event") or "message")
        data = ev.get("data") or {}
        row = ChatRunEvent(
            id=gen_id(), org_id=self.org_id, run_id=self.run_id, seq=seq, event=event, data=data
        )
        # Ordering is already guaranteed without serialising writes: ``seq`` is
        # assigned above, rows are appended in that order, and ``_flush`` holds
        # ``_flush_lock`` while inserting a batch.
        self._pending.append(row)
        if len(self._pending) >= _EVENT_BATCH_SIZE:
            await self._flush()
        elif self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._delayed_flush())
        return ev

    async def _delayed_flush(self) -> None:
        try:
            await asyncio.sleep(_EVENT_BATCH_DELAY)
            await self._flush()
        except asyncio.CancelledError:
            raise

    async def _flush(self) -> None:
        async with self._flush_lock:
            if not self._pending:
                return
            rows = self._pending
            self._pending = []
            try:
                async with SessionLocal() as s:
                    s.add_all(rows)
                    await s.commit()
            except Exception:  # noqa: BLE001
                pass

    async def heartbeat(self, **fields: Any) -> None:
        """Throttled ``tasks.progress`` update (phase, counters, timestamp)."""
        now = asyncio.get_running_loop().time()
        if now - self._last_progress_at < _PROGRESS_MIN_INTERVAL:
            return
        self._last_progress_at = now
        await self.flush_progress(**fields)

    async def flush_progress(self, **fields: Any) -> None:
        if fields.get("phase"):
            self._phase = str(fields["phase"])
        progress = {
            "last_seq": self.seq,
            "updated_at": utc_now().isoformat(),
            **({"session_id": self.session_id} if self.session_id else {}),
            **fields,
        }
        try:
            async with SessionLocal() as s:
                await s.execute(
                    update(Task)
                    .where(Task.root_run_id == self.run_id, Task.org_id == self.org_id)
                    .values(progress=progress)
                )
                await s.commit()
        except Exception:  # noqa: BLE001
            pass

    async def close(self) -> None:
        """Flush any pending insert + final heartbeat; call at end of run."""
        try:
            if self._liveness_task is not None and not self._liveness_task.done():
                self._liveness_task.cancel()
                await asyncio.gather(self._liveness_task, return_exceptions=True)
            if self._flush_task is not None and not self._flush_task.done():
                self._flush_task.cancel()
                await asyncio.gather(self._flush_task, return_exceptions=True)
            await asyncio.wait_for(self._flush(), timeout=10)
        except Exception:  # noqa: BLE001
            pass


async def fail_orphaned_chat_runs(
    db: AsyncSession, *, stale_seconds: int = CHAT_ORPHAN_STALE_SECONDS
) -> list[str]:
    """Fail chat tasks stuck in ``running`` with a stale progress heartbeat.

    A live run emits token/reasoning events and heartbeats ``tasks.progress``
    at least every few seconds; if nothing has been written for
    ``stale_seconds`` the executing worker is gone. Marking the run failed
    (instead of resuming silently) is deliberate: chat runs are not
    replayable end-to-end yet (the conversation context lives in process),
    so the honest outcome is a visible failure with a reason, and the user
    can resend.
    """
    cutoff = (utc_now() - timedelta(seconds=stale_seconds)).isoformat()
    # Deferred: agent_loop imports ChatEventRecorder from this module, so a
    # module-level import here would be circular.
    from app.core.agent_loop import _delete_trailing_user_message

    res = await db.execute(
        select(Task).where(
            Task.parent_task_id.is_(None),
            Task.status.in_(("running", "queued")),
            Task.progress["updated_at"].as_string().isnot(None),
            Task.progress["updated_at"].as_string() < cutoff,
        )
    )
    failed: list[str] = []
    for task in res.scalars().all():
        task.status = "failed"
        task.result = "worker lost: no stream activity for too long — please resend"
        task.finished_at = utc_now()
        await _delete_trailing_user_message(db, (task.progress or {}).get("session_id"))
        failed.append(task.id)
    if failed:
        await db.commit()
    return failed


async def list_events(
    db: AsyncSession, run_id: str, org_id: str, after_seq: int = 0
) -> list[ChatRunEvent]:
    res = await db.execute(
        select(ChatRunEvent)
        .where(
            ChatRunEvent.run_id == run_id,
            ChatRunEvent.org_id == org_id,
            ChatRunEvent.seq > after_seq,
        )
        .order_by(ChatRunEvent.seq)
    )
    return list(res.scalars().all())
