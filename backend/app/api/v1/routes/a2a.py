from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.a2a.server import get_exposed_agent_card, validate_a2a_agent_access
from app.core.agent_loop import run_agent_loop
from app.db.session import get_db
from app.dependencies import get_current_org_id, get_current_user
from app.models.task import Task
from app.models.user import User

router = APIRouter(prefix="/api/a2a", tags=["a2a"])


class A2ATaskRequest(BaseModel):
    agent_id: str
    input: str


class A2ATaskResponse(BaseModel):
    task_id: str
    status: str
    output: str | None = None


@router.get("/agent-card")
async def get_agent_card_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
) -> dict[str, Any]:
    """Returns the A2A Agent Card for all exposed agents in the organization."""
    return await get_exposed_agent_card(db, org_id=org_id, base_url=str(request.base_url))


@router.post("/tasks", response_model=A2ATaskResponse)
async def create_a2a_task(
    payload: A2ATaskRequest,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
) -> A2ATaskResponse:
    """Executes a task on an exposed agent via A2A protocol.

    Subject to standard authentication, authorization, quota, and guardrails.
    """
    agent = await validate_a2a_agent_access(db, org_id=org_id, agent_id=payload.agent_id)

    # Create root Task entry
    task = Task(
        org_id=org_id,
        agent_id=agent.id,
        goal=payload.input,
        status="running",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    try:
        res = await run_agent_loop(
            agent=agent,
            user_input=payload.input,
            db=db,
            user_id=current_user.id,
            root_run_id=task.id,
        )
        task.status = "succeeded"
        task.result = res.output
        await db.commit()
        return A2ATaskResponse(task_id=task.id, status="succeeded", output=res.output)
    except Exception as e:
        task.status = "failed"
        task.result = str(e)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A2A task execution failed: {e}",
        ) from e


@router.get("/tasks/{task_id}", response_model=A2ATaskResponse)
async def get_a2a_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: str = Depends(get_current_org_id),
) -> A2ATaskResponse:
    """Retrieves the status and result of an A2A task."""
    stmt = select(Task).where(Task.id == task_id, Task.org_id == org_id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    return A2ATaskResponse(task_id=task.id, status=task.status, output=task.result)
