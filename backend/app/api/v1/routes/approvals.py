from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.guardrails.approval import get_pending, resolve_approval
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
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
    dependencies=[Depends(require_permission("approvals:decide"))],
)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    return approval

