from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.config import get_settings
from app.core.agent_loop import fail_chat_run
from app.core.chat_events import (
    TERMINAL_EVENTS,
    iter_run_events,
    list_events,
    observe_delivery,
)
from app.core.observability.metrics import (
    chat_event_bus_failures_total,
    chat_event_stream_transport_total,
)
from app.core.quota.dependencies import agent_run_admission
from app.core.workflow.queue import enqueue_chat_run
from app.db.base import gen_id, utc_now
from app.db.session import SessionLocal
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.task import Task
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Statuses where GET /runs/{id}/events switches from "follow live" to
# "drain and close" — mirrored in the frontend poller.
TERMINAL_STATUSES = ("succeeded", "failed", "diverged", "cancelled", "waiting_approval")
# Floor between event-log reads while a run is actively emitting. Without it the
# drain loop re-queries as fast as the database can answer for the whole run
# (one hot loop per connected follower). Matched to the recorder's buffer window
# so this poll never becomes the reason tokens arrive in visible clumps.
LIVE_POLL_INTERVAL_SECONDS = 0.025
# Ceiling for the idle backoff below. This is the worst-case time a freshly
# written event (typically the first token, after provider warm-up) can sit in
# the log before a follower reads it, so it is a direct floor on perceived
# time-to-first-token — keep it small.
_IDLE_POLL_CEILING_SECONDS = 0.25
# How often, in idle rounds, to fall back to the task-status check that
# detects a crashed worker. The happy path terminates on TERMINAL_EVENTS in
# the log itself, so this only needs to be periodic.
_STATUS_CHECK_EVERY_N_IDLE_ROUNDS = 4
_ACTIVE_CHAT_TASKS: dict[str, asyncio.Task] = {}


async def run_chat_detached(payload: dict) -> None:
    async with SessionLocal() as db:
        request = ChatRequest.model_validate(payload)
        active_task = asyncio.current_task()
        if active_task is not None:
            _ACTIVE_CHAT_TASKS[request.run_id] = active_task
        res = await db.execute(
            select(Task).where(Task.id == request.run_id, Task.org_id == payload["org_id"])
        )
        task = res.scalar_one_or_none()
        if task is None:
            _ACTIVE_CHAT_TASKS.pop(request.run_id, None)
            return
        if task.status != "queued":
            _ACTIVE_CHAT_TASKS.pop(request.run_id, None)
            return
        task.status = "running"
        await db.commit()
        try:
            await ChatService(db).run(
                payload["org_id"],
                request,
                user_id=payload.get("user_id"),
                user_role=payload.get("user_role"),
                root_run_id=payload.get("root_run_id") or request.run_id,
                current_task_id=task.id,
                approval_resume_id=payload.get("approval_resume_id"),
            )
        except Exception as exc:  # noqa: BLE001
            await fail_chat_run(db, task, exc)
        finally:
            if _ACTIVE_CHAT_TASKS.get(request.run_id) is active_task:
                _ACTIVE_CHAT_TASKS.pop(request.run_id, None)


@router.post(
    "",
    dependencies=[Depends(require_permission("agents:run")), Depends(agent_run_admission)],
)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ChatService(db)
    if not body.stream:
        try:
            result = await svc.run(
                org_id,
                body,
                user_id=current_user.id,
                user_role=getattr(http_request.state, "role", None),
                root_run_id=body.run_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return result.model_dump()

    run_id = body.run_id or gen_id()
    chat_request = body.model_copy(update={"run_id": run_id})
    try:
        session, _agent, task = await svc.prepare_run(
            org_id,
            chat_request,
            run_id,
            user_id=current_user.id,
            user_role=getattr(http_request.state, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    chat_request = chat_request.model_copy(update={"session_id": session.id})
    payload = {
        **chat_request.model_dump(),
        "org_id": org_id,
        "user_id": current_user.id,
        "user_role": getattr(http_request.state, "role", None),
    }
    if task.status in {"succeeded", "failed", "diverged", "cancelled"}:
        run_status = task.status
    elif get_settings().workflow_execution_mode == "queued":
        await enqueue_chat_run(payload)
        task.status = "queued"
        await db.commit()
        run_status = "queued"
    else:
        background_tasks.add_task(run_chat_detached, payload)
        run_status = "running"

    async def gen():
        yield format_sse({"event": "session_start", "data": {"session_id": session.id}})
        yield format_sse(
            {
                "event": "chat_run_start",
                "data": {"run_id": run_id, "session_id": session.id, "status": run_status},
            }
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/runs/{run_id}", dependencies=[Depends(require_permission("agents:run"))])
async def get_chat_run(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Task)
        .where(Task.root_run_id == run_id, Task.org_id == org_id)
        .order_by(Task.created_at.desc())
    )
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "chat run not found")
    return {
        "id": run_id,
        "status": task.status,
        "result": task.result,
        "message": task.goal,
        "session_id": (task.progress or {}).get("session_id"),
        "error": task.result if task.status in {"failed", "diverged"} else None,
        # Live checkpoint: what the loop is doing right now (phase + last
        # event seq). Lets a polling client render "Using tool X…" etc. after
        # a reload without touching the event log.
        "progress": task.progress or {},
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


@router.post("/runs/{run_id}/cancel", dependencies=[Depends(require_permission("agents:run"))])
async def cancel_chat_run(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Task).where(Task.root_run_id == run_id, Task.org_id == org_id)
    )
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "chat run not found")
    if task.status not in TERMINAL_STATUSES:
        task.status = "cancelled"
        task.result = "Cancelled by user"
        task.finished_at = utc_now()
        task.progress = {
            **(task.progress or {}),
            "phase": "cancelled",
            "updated_at": utc_now().isoformat(),
        }
        await db.commit()
        active_task = _ACTIVE_CHAT_TASKS.get(run_id)
        if active_task is not None and active_task is not asyncio.current_task():
            active_task.cancel()
    return {"id": run_id, "status": task.status}


@router.get("/runs/{run_id}/events", dependencies=[Depends(require_permission("agents:run"))])
async def stream_chat_run_events(
    request: Request,
    run_id: str,
    follow: bool = Query(True),
    after_seq: int = Query(0, ge=0),
    org_id: str = Depends(get_current_org_id),
):
    """Drain the durable event log of a chat run, optionally following live.

    Replay: a client that reloaded mid-run calls this once, rebuilds the UI
    from the drained events (partial text, reasoning, running tool cards),
    then keeps the connection open to receive the rest of the run live.
    ``follow=false`` returns a one-shot JSON snapshot instead of SSE.

    Every database read uses a short-lived session. The SSE generator can stay
    open for minutes, so retaining a request-scoped session here would leave
    its transaction ``idle in transaction`` and exhaust the API pool for
    unrelated requests such as login.
    """
    async with SessionLocal() as session:
        res = await session.execute(
            select(Task).where(Task.root_run_id == run_id, Task.org_id == org_id)
        )
        task = res.scalars().first()
        if task is None:
            raise HTTPException(404, "chat run not found")
        task_status = task.status
        snapshot_rows = (
            await list_events(session, run_id, org_id, after_seq) if not follow else None
        )

    if not follow:
        return {
            "run_id": run_id,
            "status": task_status,
            "events": [
                {"seq": r.seq, "event": r.event, "data": r.data or {}}
                for r in snapshot_rows or []
            ],
        }

    async def gen():
        last = after_seq
        terminal_seen = False

        async def drain_log() -> AsyncIterator[str]:
            """Emit everything already durable past ``last``."""
            nonlocal last, terminal_seen
            async with SessionLocal() as session:
                rows = await list_events(session, run_id, org_id, last)
            for r in rows:
                last = r.seq
                observe_delivery(run_id, r.seq, "polling")
                if r.event in TERMINAL_EVENTS:
                    terminal_seen = True
                yield format_sse({"event": r.event, "data": {"seq": r.seq, **(r.data or {})}})

        async def task_is_over() -> bool:
            async with SessionLocal() as s:
                status = (
                    await s.execute(
                        select(Task.status).where(
                            Task.root_run_id == run_id, Task.org_id == org_id
                        )
                    )
                ).scalar()
            return status in TERMINAL_STATUSES

        # --- Fast path: live fan-out over the event bus ---------------------
        # Subscribe *before* draining the log so an event produced during the
        # drain is buffered by the subscription instead of falling in the gap
        # between the two. Duplicates are then filtered by seq.
        subscription = None
        try:
            subscription = iter_run_events(org_id, run_id)
            # Consumes only the ready signal, never a real event.
            await subscription.__anext__()
        except StopAsyncIteration:
            subscription = None
        except Exception:  # noqa: BLE001
            chat_event_bus_failures_total.labels("subscribe").inc()
            subscription = None

        if subscription is not None:
            chat_event_stream_transport_total.labels("pubsub").inc()
            try:
                async for chunk in drain_log():
                    yield chunk
                if terminal_seen:
                    return
                if await task_is_over():
                    async for chunk in drain_log():
                        yield chunk
                    return
                async for message in subscription:
                    if await request.is_disconnected():
                        return
                    if message is None:
                        # Idle tick: keep proxies from closing the connection and
                        # notice a worker that died without writing a terminal event.
                        if await task_is_over():
                            async for chunk in drain_log():
                                yield chunk
                            return
                        yield ": heartbeat\n\n"
                        continue
                    seq = message.get("seq")
                    if isinstance(seq, int):
                        if seq <= last:
                            continue  # already delivered by the drain above
                        if seq > last + 1:
                            # Gap: something between `last` and `seq` never
                            # reached this subscriber live (e.g. the circuit
                            # breaker tripped for one publish). The durable log
                            # is written regardless of bus health, so backfill
                            # from it before trusting this message.
                            async for chunk in drain_log():
                                yield chunk
                            if terminal_seen:
                                return
                            if seq <= last:
                                continue  # recovered by the backfill above
                        last = seq
                    observe_delivery(run_id, seq, "pubsub")
                    event = str(message.get("event") or "message")
                    yield format_sse(
                        {"event": event, "data": {"seq": seq, **(message.get("data") or {})}}
                    )
                    if event in TERMINAL_EVENTS:
                        # The durable write can lag the publish by design (fan-out
                        # never waits on it — see ChatEventRecorder.record), so a
                        # straggler event may not be durable yet even though the
                        # run just finished. One last drain reconciles before
                        # closing so nothing is silently lost.
                        async for chunk in drain_log():
                            yield chunk
                        return
                return
            finally:
                await subscription.aclose()

        # --- Fallback: poll the durable log --------------------------------
        # Reached when the bus is unavailable. Slower, but chat keeps working;
        # the transport counter above makes the degradation visible.
        chat_event_stream_transport_total.labels("polling").inc()
        idle_rounds = 0
        while True:
            # Client went away (reload / Stop) — stop polling the DB.
            if await request.is_disconnected():
                return
            async with SessionLocal() as session:
                rows = await list_events(session, run_id, org_id, last)
            for r in rows:
                last = r.seq
                observe_delivery(run_id, r.seq, "polling")
                if r.event in TERMINAL_EVENTS:
                    terminal_seen = True
                yield format_sse({"event": r.event, "data": {"seq": r.seq, **(r.data or {})}})
            if terminal_seen:
                return
            if rows:
                idle_rounds = 0
                await asyncio.sleep(LIVE_POLL_INTERVAL_SECONDS)
                continue
            # The task-status fallback only matters when the log goes quiet
            # (crashed worker); checking it on every idle round doubles the
            # query cost of a tight poll for no benefit.
            if idle_rounds % _STATUS_CHECK_EVERY_N_IDLE_ROUNDS == 0 and await task_is_over():
                return  # log fully drained above; run is over
            idle_rounds += 1
            # Back off gently while the run is quiet, but keep the ceiling low:
            # a live run that has not emitted yet is the normal state during
            # provider warm-up / prompt processing, and this sleep is exactly
            # how long the *first* token then sits in the log unread.
            await asyncio.sleep(min(_IDLE_POLL_CEILING_SECONDS, 0.05 * (2**idle_rounds)))
            yield ": heartbeat\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
