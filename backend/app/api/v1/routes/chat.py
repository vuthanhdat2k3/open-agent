from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.config import get_settings
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


async def _run_chat_detached(payload: dict) -> None:
    async with SessionLocal() as db:
        request = ChatRequest.model_validate(payload)
        res = await db.execute(
            select(Task).where(Task.id == request.run_id, Task.org_id == payload["org_id"])
        )
        task = res.scalar_one_or_none()
        if task is None:
            return
        try:
            await ChatService(db).run(
                payload["org_id"],
                request,
                user_id=payload.get("user_id"),
                root_run_id=request.run_id,
                current_task_id=task.id,
            )
        except Exception as exc:  # noqa: BLE001
            task.status = "failed"
            task.result = str(exc)
            task.finished_at = utc_now()
            await db.commit()


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
        background_tasks.add_task(_run_chat_detached, payload)
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
        "error": task.result if task.status in {"failed", "diverged"} else None,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }
