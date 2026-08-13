from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import EmailConnection
from app.models.job_schedule import JobScheduleExecution
from app.models.outbox import OutboxEvent

router = APIRouter(
    prefix="/api/admin/email-intelligence",
    tags=["email-intelligence-admin"],
    dependencies=[Depends(require_permission("admin:email-intelligence"))],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/overview")
async def overview(org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    healthy = await db.scalar(select(func.count(EmailConnection.id)).where(EmailConnection.org_id == org_id, EmailConnection.status == "connected"))
    total_connections = await db.scalar(select(func.count(EmailConnection.id)).where(EmailConnection.org_id == org_id))
    ready = await db.scalar(select(func.count(OutboxEvent.id)).where(OutboxEvent.org_id == org_id, OutboxEvent.status == "pending"))
    retrying = await db.scalar(select(func.count(OutboxEvent.id)).where(OutboxEvent.org_id == org_id, OutboxEvent.status == "retrying"))
    dead_letter = await db.scalar(select(func.count(OutboxEvent.id)).where(OutboxEvent.org_id == org_id, OutboxEvent.status == "dead_letter"))
    reviews = await db.scalar(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.org_id == org_id, ApprovalRequest.status == "pending", ApprovalRequest.case_id.is_not(None)))
    return {
        "connections": {"total": int(total_connections or 0), "healthy": int(healthy or 0), "unhealthy": int((total_connections or 0) - (healthy or 0))},
        "queue": {"ready": int(ready or 0), "retrying": int(retrying or 0), "oldest_age_seconds": 0, "dead_letter": int(dead_letter or 0)},
        "reviews": {"open": int(reviews or 0), "due_soon": 0, "breached": 0},
        "scheduler": {"healthy": True, "missed_occurrences": 0},
        "capabilities": {"can_view_connections": True, "can_view_queue": True, "can_retry_dead_letter": False, "can_resolve_reviews": False},
        "meta": {"server_time": _now().isoformat()},
    }


@router.get("/schedulers")
async def schedulers(org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(JobScheduleExecution).order_by(JobScheduleExecution.scheduled_for.desc()).limit(100))
    return [{"id": row.id, "job_key": row.job_key, "scheduled_for": row.scheduled_for, "status": row.status, "attempt": row.attempt, "lease_expires_at": row.lease_expires_at, "started_at": row.started_at, "finished_at": row.finished_at, "error": row.error, "capabilities": {"can_retry": False}} for row in rows]


@router.get("/queue")
async def queue(org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db), status: str | None = Query(None)):
    stmt = select(OutboxEvent).where(OutboxEvent.org_id == org_id).order_by(OutboxEvent.created_at.desc()).limit(100)
    if status:
        stmt = stmt.where(OutboxEvent.status == status)
    rows = await db.scalars(stmt)
    return [{"id": row.id, "event_type": row.event_type, "aggregate_type": row.aggregate_type, "aggregate_id": row.aggregate_id, "status": row.status, "attempt_count": row.attempt_count, "available_at": row.available_at, "last_error_code": row.last_error_code, "correlation_id": row.correlation_id, "created_at": row.created_at, "capabilities": {"can_retry": False}} for row in rows]


@router.get("/reviews")
async def reviews(org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(ApprovalRequest).where(ApprovalRequest.org_id == org_id, ApprovalRequest.status == "pending", ApprovalRequest.case_id.is_not(None)).order_by(ApprovalRequest.created_at.asc()).limit(100))
    return [{"id": row.id, "execution_id": row.run_id, "action_type": row.tool_name or row.run_type, "title": row.tool_name or "Ambiguous action", "status": "OPEN", "ambiguity_code": "PROVIDER_RESULT_UNKNOWN", "opened_at": row.created_at, "due_at": row.expires_at, "sla_status": "NORMAL", "risk_level": "HIGH", "capabilities": {"can_view_detail": True, "can_resolve": False, "blocked_reasons": {"resolve": "capability.admin_resolution_policy_disabled"}}} for row in rows]


@router.get("/traces")
async def traces(
    correlation_id: str = Query(..., min_length=3, max_length=128),
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.scalars(select(OutboxEvent).where(OutboxEvent.org_id == org_id, OutboxEvent.correlation_id == correlation_id).order_by(OutboxEvent.created_at.asc()).limit(100))
    return {"events": [{"event_id": row.id, "lifecycle": row.aggregate_type, "event_type": row.event_type, "state": row.status, "reason_codes": [row.last_error_code] if row.last_error_code else [], "occurred_at": row.created_at, "causation_id": row.causation_id} for row in rows], "capabilities": {"can_view_sensitive_detail": False}, "meta": {"server_time": _now().isoformat()}}
