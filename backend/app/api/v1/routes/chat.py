from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.config import get_settings
from app.core.chat_events import TERMINAL_EVENTS, list_events
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
                root_run_id=request.run_id,
                current_task_id=task.id,
                approval_resume_id=payload.get("approval_resume_id"),
            )
        except Exception as exc:  # noqa: BLE001
            task.status = "failed"
            task.result = str(exc)
            task.finished_at = utc_now()
            await db.commit()
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
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ChatService(db)
    if not body.stream:
        result = await svc.run(org_id, body, user_id=current_user.id, root_run_id=body.run_id)
        return result.model_dump()

    run_id = body.run_id or gen_id()
    request = body.model_copy(update={"run_id": run_id})
    session, _agent, task = await svc.prepare_run(
        org_id, request, run_id, user_id=current_user.id
    )
    request = request.model_copy(update={"session_id": session.id})
    payload = {
        **request.model_dump(),
        "org_id": org_id,
        "user_id": current_user.id,
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
        .order_by(Task.created_at)
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
    db: AsyncSession = Depends(get_db),
):
    """Drain the durable event log of a chat run, optionally following live.

    Replay: a client that reloaded mid-run calls this once, rebuilds the UI
    from the drained events (partial text, reasoning, running tool cards),
    then keeps the connection open to receive the rest of the run live.
    ``follow=false`` returns a one-shot JSON snapshot instead of SSE.
    """
    res = await db.execute(
        select(Task).where(Task.root_run_id == run_id, Task.org_id == org_id)
    )
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "chat run not found")

    if not follow:
        rows = await list_events(db, run_id, org_id, after_seq)
        return {
            "run_id": run_id,
            "status": task.status,
            "events": [
                {"seq": r.seq, "event": r.event, "data": r.data or {}} for r in rows
            ],
        }

    async def gen():
        last = after_seq
        terminal_seen = False
        idle_rounds = 0
        while True:
            # Client went away (reload / Stop) — stop polling the DB.
            if await request.is_disconnected():
                return
            rows = await list_events(db, run_id, org_id, last)
            for r in rows:
                last = r.seq
                if r.event in TERMINAL_EVENTS:
                    terminal_seen = True
                yield format_sse({"event": r.event, "data": {"seq": r.seq, **(r.data or {})}})
            if terminal_seen:
                return
            if rows:
                idle_rounds = 0
                continue
            async with SessionLocal() as s:
                status = (
                    await s.execute(
                        select(Task.status).where(
                            Task.root_run_id == run_id, Task.org_id == org_id
                        )
                    )
                ).scalar()
            if status in TERMINAL_STATUSES:
                return  # log fully drained above; run is over
            idle_rounds += 1
            # Back off gently when the run is quiet instead of hammering the
            # DB at a fixed rate (cheap win on Postgres + SQLite alike).
            await asyncio.sleep(min(2.0, 0.25 * (2**idle_rounds)) if idle_rounds > 1 else 0.25)
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
