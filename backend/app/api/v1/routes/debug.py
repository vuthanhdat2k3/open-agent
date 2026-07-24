from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.models.task import Task
from app.services.debug_service import DebugService

router = APIRouter(
    prefix="/api/debug",
    tags=["debug"],
)


@router.get("/sessions", dependencies=[Depends(require_permission("usage:read"))])
async def list_sessions(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await DebugService(db).list_sessions(org_id)


@router.get("/sessions/{session_id}", dependencies=[Depends(require_permission("usage:read"))])
async def session_tree(
    session_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await DebugService(db).get_session_tree(org_id, session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/usage", dependencies=[Depends(require_permission("usage:read"))])
async def usage_summary(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await DebugService(db).usage_summary(org_id)


@router.get("/agents", dependencies=[Depends(require_permission("agents:read"))])
async def list_agents(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await DebugService(db).list_agents(org_id)


@router.get("/tasks/{root_run_id}", dependencies=[Depends(require_permission("usage:read"))])
async def task_tree(
    root_run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Task)
        .where(Task.org_id == org_id, Task.root_run_id == root_run_id)
        .order_by(Task.created_at)
    )
    tasks = list(res.scalars().all())
    if not tasks:
        raise HTTPException(404, "task tree not found")

    nodes = {
        task.id: {
            "id": task.id,
            "org_id": task.org_id,
            "parent_task_id": task.parent_task_id,
            "root_run_id": task.root_run_id,
            "agent_id": task.agent_id,
            "goal": task.goal,
            "status": task.status,
            "result": task.result,
            "cost_usd": task.cost_usd,
            "token_usage": task.token_usage,
            "depth": task.depth,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "created_at": task.created_at,
            "children": [],
        }
        for task in tasks
    }
    roots: list[dict] = []
    for task in tasks:
        node = nodes[task.id]
        if task.parent_task_id and task.parent_task_id in nodes:
            nodes[task.parent_task_id]["children"].append(node)
        else:
            roots.append(node)
    return {"root_run_id": root_run_id, "tasks": roots}
