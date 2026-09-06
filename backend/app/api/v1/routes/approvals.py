from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.chat import run_chat_detached
from app.config import get_settings
from app.core.authz.policy import PrincipalContext
from app.core.guardrails.approval import get_pending, resolve_approval
from app.core.observability.audit import log_action
from app.core.workflow.jobs import run_workflow_detached
from app.core.workflow.queue import enqueue_chat_run, enqueue_workflow_run
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.approval_request import ApprovalRequest
from app.models.task import Task
from app.models.user import User
from app.models.workflow_run import WorkflowRun

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
    requester_email: str | None = None
    requester_name: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    reason: str = ""
    created_at: datetime
    expires_at: datetime | None = None
    title: str | None = None
    instructions: str = ""
    approver_user_ids: list[str] | None = None
    risk_level: str = "MEDIUM"
    approval_mode: str = "EXPLICIT"
    capabilities: dict[str, Any] = {}
    server_time: datetime | None = None

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    decision: str
    reason: str = ""


@router.get(
    "",
    response_model=list[ApprovalOut],
)
async def list_approvals(
    include_chat: bool = False,
    run_id: str | None = None,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("approvals:read")),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now()
    is_admin = authz.allows("approvals:manage")
    exclude_run_types = [] if include_chat else ["agent"]
    approvals = await get_pending(db, org_id=org_id, exclude_run_types=exclude_run_types, run_id=run_id)

    # Join User to get requester email/name
    user_ids = [a.requested_by for a in approvals if a.requested_by]
    user_map: dict[str, User] = {}
    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in res.scalars().all():
            user_map[u.id] = u

    result = []
    for approval in approvals:
        owner = (
            current_user.id in approval.approver_user_ids
            if approval.approver_user_ids
            else (is_admin or approval.requested_by == current_user.id)
        )
        action = approval.tool_name or approval.node_id or approval.run_type
        risk_level = "HIGH" if approval.case_id or approval.tool_name else "MEDIUM"
        requester_email = user_map[approval.requested_by].email if approval.requested_by and approval.requested_by in user_map else None
        requester_name = user_map[approval.requested_by].display_name if approval.requested_by and approval.requested_by in user_map else None
        result.append(
            {
                "id": approval.id,
                "org_id": approval.org_id,
                "run_type": approval.run_type,
                "run_id": approval.run_id,
                "tool_name": approval.tool_name,
                "node_id": approval.node_id,
                "args_snapshot": approval.args_snapshot,
                "status": approval.status,
                "requested_by": approval.requested_by,
                "requester_email": requester_email,
                "requester_name": requester_name,
                "decided_by": approval.decided_by,
                "decided_at": approval.decided_at,
                "reason": approval.reason,
                "created_at": approval.created_at,
                "case_id": approval.case_id,
                "action": action,
                "expires_at": approval.expires_at,
                "title": approval.title,
                "instructions": approval.instructions,
                "approver_user_ids": approval.approver_user_ids,
                "risk_level": risk_level,
                "approval_mode": "EXPLICIT",
                "capabilities": {
                    "can_view_detail": owner,
                    "can_approve": owner,
                    "can_reject": owner,
                    "blocked_reasons": {} if owner else {"approve": "capability.not_owner"},
                },
                "server_time": now,
            }
        )
    return result


@router.post(
    "/{approval_id}/decide",
    response_model=ApprovalOut,
)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    background_tasks: BackgroundTasks,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("approvals:read")),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    approval_lookup = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.org_id == org_id,
        )
    )
    requested_approval = approval_lookup.scalar_one_or_none()
    if requested_approval is None:
        raise HTTPException(status_code=404, detail="approval request not found")

    if requested_approval.approver_user_ids:
        # A workflow `approval` node named specific approvers: that allow-list
        # is the whole point of the field, so it overrides the generic
        # requested-by/admin rule below rather than adding to it.
        if current_user.id not in requested_approval.approver_user_ids:
            raise HTTPException(status_code=403, detail="You are not an authorized approver for this request")
    # Users may decide approvals they requested or that were triggered on their behalf
    # (for example, their own chat tool executions / email drafts);
    # admins with approvals:manage retain organization-wide decision authority.
    elif not authz.allows("approvals:manage"):
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
                Task.status.in_(["waiting_approval", "running", "pending", "queued"]),
                # `root_run_id` is shared by the root task and every nested
                # delegated sub-task spawned under it (see agent_loop.py's
                # nested-resume recursion), so this filter alone is
                # ambiguous whenever more than one of them is paused at
                # once - e.g. a sub-agent's *own* new tool call also hits an
                # approval gate while it is mid-resume, leaving both the
                # root and that sub-task at `waiting_approval`
                # simultaneously. Only the root task (no parent) is ever
                # meant to be resumed directly here; agent_loop.py's
                # `_find_direct_child_toward` walks down to whichever
                # delegated sub-agent actually owns the approval.
                Task.parent_task_id.is_(None),
            )
        )
        task = task_res.scalars().first()
        if task is not None:
            task.status = "queued"
            # Reset finished_at so the task is treated as live again.
            # When a sub-agent hits an approval gate, _finish_task() sets
            # finished_at on the root task. Without clearing it here the
            # resumed run looks "done" to any observer that relies on
            # finished_at being NULL for in-progress tasks.
            task.finished_at = None
            task.progress = {
                **(task.progress or {}),
                "phase": "queued",
                "approval_id": approval.id,
                "approval_decision": approval.status,
            }
            await db.commit()
            principal = task.execution_principal or {}
            payload = {
                "agent_id": task.agent_id,
                "message": task.goal,
                # Reuse the root chat session so the resumed run's messages
                # land back in the same conversation the user is looking
                # at, instead of a disconnected session with none of the
                # prior turns. `task` here is always the *root* task (looked
                # up by `root_run_id`), so its `agent_id` is the same agent
                # the session was created for on the first turn - passing
                # this session_id through can never trip ChatService's
                # "session belongs to a different agent" check. The session
                # id is persisted once in `task.progress["session_id"]` when
                # the root task is first created (see
                # ChatService.prepare_run) and never changes afterwards, so
                # it is safe to reuse across any number of approval
                # round-trips through delegated sub-agents.
                "session_id": (task.progress or {}).get("session_id"),
                "run_id": task.id,
                "root_run_id": approval.run_id,
                "stream": True,
                "org_id": org_id,
                "user_id": principal.get("user_id") or task.triggered_by_user_id,
                "user_role": principal.get("role"),
                "approval_resume_id": approval.id,
                "model_id": (task.progress or {}).get("model_id"),
                "prepared": True,
                "prepared_agent_release_id": task.agent_release_id,
            }
            if get_settings().workflow_execution_mode == "queued":
                await enqueue_chat_run(payload)
            else:
                background_tasks.add_task(run_chat_detached, payload)
    if approval.run_type in {"workflow", "workflow.tool"} and approval.run_id:
        # A workflow approval node paused the run at `waiting_approval`.
        # Without this branch the decision is recorded but nothing ever drives
        # the run again — it stays waiting forever. Flip it back to a live
        # status and hand it to the executor; the engine consults the decided
        # approval request when it re-enters the gate node (continue on
        # approved, fail the node on rejected).
        run_res = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == approval.run_id,
                WorkflowRun.org_id == org_id,
            )
        )
        workflow_run = run_res.scalar_one_or_none()
        if workflow_run is not None and workflow_run.status in {"waiting_approval", "queued"}:
            workflow_run.status = "running"
            workflow_run.error = None
            await db.commit()
            if get_settings().workflow_execution_mode == "queued":
                await enqueue_workflow_run(workflow_run.id)
            else:
                background_tasks.add_task(run_workflow_detached, workflow_run.id)
    return approval
