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
import json
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.observability.metrics import (
    chat_event_bus_failures_total,
    chat_event_fanout_seconds,
)
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

# --- Live event bus ---------------------------------------------------------
# The durable log above is what makes a reload recoverable, but reading it back
# by polling is what made streaming feel laggy: an event was only visible once
# a follower's next poll came around. The bus below fans events out the moment
# they are produced; the log stays authoritative for replay and as the fallback
# transport when the bus is unavailable.
#
# Publishing must never slow the agent loop down. If Redis is unreachable an
# `await publish` would otherwise pay a connect timeout *per event*, so a
# failure trips a short circuit breaker and every publish is skipped (silently
# degrading to the polling path) until it expires.
_BUS_SOCKET_TIMEOUT = 0.5
_BUS_BREAKER_COOLDOWN = 30.0
_bus_client: Any = None
_bus_breaker_until = 0.0

# --- Fan-out latency instrumentation ----------------------------------------
# Records when each event was produced so a follower can report how long the
# transport took to hand it over. Kept in-process (and therefore only populated
# in inline mode) on purpose: putting the timestamp on the wire would leak a
# measurement artefact into the client payload, and a wall-clock comparison
# across processes would measure clock skew as much as latency.
_RECORD_TIME_CAP = 10_000
_record_times: dict[tuple[str, int], float] = {}


def _note_record_time(run_id: str, seq: int) -> None:
    if len(_record_times) < _RECORD_TIME_CAP:
        _record_times[(run_id, seq)] = time.time()


def observe_delivery(run_id: str, seq: Any, transport: str) -> None:
    """Report fan-out latency for one delivered event. Safe to call blindly."""
    if not isinstance(seq, int):
        return
    started = _record_times.pop((run_id, seq), None)
    if started is None:
        return  # produced in another process, or already observed
    chat_event_fanout_seconds.labels(transport).observe(max(0.0, time.time() - started))


def run_channel(org_id: str, run_id: str) -> str:
    """Channel name for one run. Scoped by org so a guessed run id is inert."""
    return f"chat:events:{org_id}:{run_id}"


def _monotonic() -> float:
    try:
        return asyncio.get_running_loop().time()
    except RuntimeError:
        return 0.0


def _bus_available() -> bool:
    return _monotonic() >= _bus_breaker_until


def _trip_breaker(operation: str) -> None:
    global _bus_breaker_until, _bus_client
    chat_event_bus_failures_total.labels(operation).inc()
    _bus_breaker_until = _monotonic() + _BUS_BREAKER_COOLDOWN
    # Drop the client so the next attempt after the cooldown reconnects instead
    # of reusing a connection that is already known to be broken.
    _bus_client = None


async def _get_bus_client() -> Any:
    """Lazily build the shared Redis client used for pub/sub fan-out."""
    global _bus_client
    if _bus_client is not None:
        return _bus_client
    from redis.asyncio import from_url

    _bus_client = from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_timeout=_BUS_SOCKET_TIMEOUT,
        socket_connect_timeout=_BUS_SOCKET_TIMEOUT,
    )
    return _bus_client


async def publish_run_event(org_id: str, run_id: str, payload: dict[str, Any]) -> None:
    """Fan one event out to live followers. Never raises, never blocks for long."""
    if not _bus_available():
        return
    try:
        client = await _get_bus_client()
        await asyncio.wait_for(
            client.publish(run_channel(org_id, run_id), json.dumps(payload)),
            timeout=_BUS_SOCKET_TIMEOUT,
        )
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        _trip_breaker("publish")


async def iter_run_events(
    org_id: str, run_id: str, idle_tick: float = _LIVENESS_INTERVAL
) -> AsyncIterator[dict[str, Any] | None]:
    """Yield live events for one run, or ``None`` every ``idle_tick`` seconds.

    The ``None`` ticks let the caller emit an SSE heartbeat and re-check the
    task status (crashed-worker detection) without needing its own timer. Raises
    on subscription failure so the caller can fall back to polling.
    """
    client = await _get_bus_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(run_channel(org_id, run_id))
    try:
        # Ready signal. The caller needs a way to know the subscription is live
        # before it starts draining the durable log, but it must not have to
        # pull a message to find out: the first message pulled would be
        # consumed by that handshake and never delivered. Yielding immediately
        # here keeps "subscribed" and "received an event" separate concerns.
        yield None
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=idle_tick
            )
            if message is None:
                yield None
                continue
            raw = message.get("data")
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except (TypeError, ValueError):
                continue
    finally:
        try:
            await pubsub.unsubscribe(run_channel(org_id, run_id))
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass


class ChatEventRecorder:
    """Append events for one chat run; yield them through unchanged.

    Every write goes through ``SessionLocal`` (its own short transaction), so
    recording works identically in the inline API process and in the arq
    worker, and never entangles the request-scoped session the agent loop
    commits on.
    """

    def __init__(
        self,
        org_id: str,
        run_id: str,
        session_id: str | None = None,
        model_id: str | None = None,
    ):
        self.org_id = org_id
        self.run_id = run_id
        self.session_id = session_id
        self.model_id = model_id
        self.seq = 0
        self._pending: list[ChatRunEvent] = []
        self._flush_task: asyncio.Task | None = None
        self._flush_lock = asyncio.Lock()
        self._liveness_task: asyncio.Task | None = None
        self._progress_task: asyncio.Task | None = None
        self._phase = "queued"
        self._last_progress_at = 0.0

    async def sync_seq_from_db(self, db: AsyncSession | None = None) -> int:
        """Synchronize self.seq with the highest existing sequence number in DB."""
        if db is not None:
            res = await db.execute(
                select(func.coalesce(func.max(ChatRunEvent.seq), 0)).where(
                    ChatRunEvent.run_id == self.run_id
                )
            )
            self.seq = int(res.scalar() or 0)
            return self.seq
        async with SessionLocal() as session:
            res = await session.execute(
                select(func.coalesce(func.max(ChatRunEvent.seq), 0)).where(
                    ChatRunEvent.run_id == self.run_id
                )
            )
            self.seq = int(res.scalar() or 0)
            return self.seq

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
        if self.seq == 0 and not self._pending:
            try:
                await self.sync_seq_from_db()
            except Exception:
                pass
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
        _note_record_time(self.run_id, seq)
        # Fan out before the database round trip: the log write is what makes
        # the event durable, but followers should not wait for it.
        await publish_run_event(
            self.org_id, self.run_id, {"seq": seq, "event": event, "data": data}
        )
        if event == "message_done":
            await self._flush()
            return ev
        # Both triggers below schedule the write as a background task rather
        # than awaiting it here: this coroutine is inline in the LLM stream
        # read loop, so awaiting a DB round trip would stall token delivery
        # to the client every _EVENT_BATCH_SIZE tokens. `_flush_lock` already
        # serializes concurrent flushes, so overlap between the two triggers
        # is safe (the loser just finds `_pending` empty and returns).
        if len(self._pending) >= _EVENT_BATCH_SIZE:
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._flush())
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
        """Throttled ``tasks.progress`` update (phase, counters, timestamp).

        Scheduled as a background task rather than awaited: this is called
        inline in the per-token streaming loop (once per throttle window),
        so awaiting the DB round trip here would stall delivery of the next
        token for as long as the write takes — this was the actual cause of
        a ~1s stall roughly once a second, not the event-log batching.
        """
        now = asyncio.get_running_loop().time()
        if now - self._last_progress_at < _PROGRESS_MIN_INTERVAL:
            return
        self._last_progress_at = now
        if self._progress_task is None or self._progress_task.done():
            self._progress_task = asyncio.create_task(self.flush_progress(**fields))

    async def flush_progress(self, **fields: Any) -> None:
        if fields.get("phase"):
            self._phase = str(fields["phase"])
        progress = {
            "last_seq": self.seq,
            "updated_at": utc_now().isoformat(),
            **({"session_id": self.session_id} if self.session_id else {}),
            **({"model_id": self.model_id} if self.model_id else {}),
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
                # Do not cancel: since record() started scheduling the
                # size-triggered flush as a background task too, this may be
                # a real in-flight insert (not just the delayed-flush timer),
                # and cancelling it mid-write drops that batch permanently.
                await asyncio.gather(self._flush_task, return_exceptions=True)
            if self._progress_task is not None and not self._progress_task.done():
                await asyncio.gather(self._progress_task, return_exceptions=True)
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
