from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.scope import scope_to_owner
from app.core.tools.authorization import tool_args_hash
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
    owning_task_id: str | None = None,
    idempotency_key: str | None = None,
) -> ApprovalRequest:
    if idempotency_key:
        existing = await db.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.org_id == org_id,
                ApprovalRequest.idempotency_key == idempotency_key,
                ApprovalRequest.status == "pending",
            )
        )
        if existing is not None:
            return existing
    approval = ApprovalRequest(
        org_id=org_id,
        run_type=run_type,
        run_id=run_id,
        tool_name=tool_name,
        node_id=node_id,
        args_snapshot=args_snapshot or {},
        requested_by=requested_by,
        status="pending",
        owning_task_id=owning_task_id,
        payload_hash=tool_args_hash(args_snapshot or {}) if tool_name else None,
        idempotency_key=idempotency_key,
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


async def get_pending(
    db: AsyncSession,
    *,
    org_id: str,
    exclude_run_types: list[str] | tuple[str, ...] | None = None,
    run_id: str | None = None,
) -> list[ApprovalRequest]:
    base_filter = [ApprovalRequest.org_id == org_id, ApprovalRequest.status == "pending"]
    if exclude_run_types:
        base_filter.append(ApprovalRequest.run_type.not_in(exclude_run_types))
    if run_id:
        base_filter.append(ApprovalRequest.run_id == run_id)
    stmt = scope_to_owner(
        select(ApprovalRequest).where(*base_filter),
        db,
        ApprovalRequest.requested_by,
    )
    res = await db.execute(stmt.order_by(ApprovalRequest.created_at))
    return list(res.scalars().all())

