from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.approval_request import ApprovalRequest

VALID_DECISIONS = {"approved", "rejected"}


async def request_approval(
    db: AsyncSession,
    *,
    org_id: str,
    run_type: str,
    run_id: str | None,
    tool_name: str | None = None,
    node_id: str | None = None,
    args_snapshot: dict[str, Any] | None = None,
    requested_by: str | None = None,
) -> ApprovalRequest:
    approval = ApprovalRequest(
        org_id=org_id,
        run_type=run_type,
        run_id=run_id,
        tool_name=tool_name,
        node_id=node_id,
        args_snapshot=args_snapshot or {},
        requested_by=requested_by,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval


async def resolve_approval(
    db: AsyncSession,
    *,
    approval_id: str,
    org_id: str,
    decision: str,
    decided_by: str | None,
    reason: str = "",
) -> ApprovalRequest | None:
    if decision not in VALID_DECISIONS:
        raise ValueError("decision must be 'approved' or 'rejected'")
    res = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.org_id == org_id,
        )
    )
    approval = res.scalar_one_or_none()
    if approval is None:
        return None
    # Decision retries are safe: the first decision is authoritative and the
    # caller can reconcile its UI from it without scheduling execution again.
    if approval.status != "pending":
        return approval
    approval.status = decision
    approval.decided_by = decided_by
    approval.decided_at = utc_now()
    approval.reason = reason
    await db.commit()
    await db.refresh(approval)
    return approval


async def get_pending(db: AsyncSession, *, org_id: str) -> list[ApprovalRequest]:
    res = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.org_id == org_id, ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at)
    )
    return list(res.scalars().all())

