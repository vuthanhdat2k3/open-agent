from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.chat import run_chat_detached
from app.config import get_settings
from app.core.guardrails.approval import get_pending, resolve_approval
from app.core.observability.audit import log_action
from app.core.workflow.queue import enqueue_chat_run
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.approval_request import ApprovalRequest
from app.models.task import Task
from app.models.user import User

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ApprovalOut(BaseModel):
    id: str
    org_id: str
    run_type: str
    run_id: str | None = None
    tool_name: str | None = None
    node_id: str | None = None
    args_snapshot: dict[str, Any]
    status: str
    requested_by: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    reason: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    decision: str
    reason: str = ""


@router.get(
    "",
    response_model=list[ApprovalOut],
    dependencies=[Depends(require_permission("approvals:read"))],
)
async def list_approvals(
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_pending(db, org_id=org_id)


@router.post(
    "/{approval_id}/decide",
    response_model=ApprovalOut,
    dependencies=[Depends(require_permission("approvals:read"))],
)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    background_tasks: BackgroundTasks,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Users may decide only approvals they requested (for example, their own
    # Gmail draft); admins retain organization-wide decision authority.
    if getattr(request.state, "role", "user") != "admin":
        owner_res = await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.org_id == org_id,
                ApprovalRequest.requested_by == current_user.id,
            )
        )
        if owner_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="Users may decide only their own approvals")
    try:
        approval = await resolve_approval(
            db,
            approval_id=approval_id,
            org_id=org_id,
            decision=body.decision,
            decided_by=current_user.id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if approval is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=current_user.id,
        action="approval.decided",
        resource_type="approval_request",
        resource_id=approval.id,
        metadata={"decision": body.decision, "reason": body.reason},
    )
    if approval.run_type == "agent" and approval.run_id:
        task_res = await db.execute(
            select(Task).where(
                Task.root_run_id == approval.run_id,
                Task.org_id == org_id,
                Task.status == "waiting_approval",
            )
        )
        task = task_res.scalars().first()
        if task is not None:
            task.status = "queued"
            task.progress = {
                **(task.progress or {}),
                "phase": "queued",
                "approval_id": approval.id,
                "approval_decision": approval.status,
            }
            await db.commit()
            payload = {
                "agent_id": task.agent_id,
                "message": task.goal,
                # Delegated workers may inherit the parent chat's session
                # checkpoint; resuming with it would fail agent ownership
                # validation. ChatService creates a worker-owned session.
                "session_id": None,
                "run_id": task.id,
                "root_run_id": approval.run_id,
                "stream": True,
                "org_id": org_id,
                "user_id": current_user.id,
                "approval_resume_id": approval.id,
            }
            if get_settings().workflow_execution_mode == "queued":
                await enqueue_chat_run(payload)
            else:
                background_tasks.add_task(run_chat_detached, payload)
    return approval
