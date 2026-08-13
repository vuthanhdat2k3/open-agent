"""Explicit, checkpointed clean cutover for agent email classification."""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import (
    BriefingReport,
    CiConnectionCutover,
    CiNotification,
    DeliveryAttempt,
    EmailConnection,
    InboundEmail,
    Meeting,
    ResearchCase,
    ResearchSource,
)
from app.models.outbox import OutboxEvent


async def clean_cutover(
    db: AsyncSession,
    *,
    org_id: str,
    connection_id: str,
    cutover_history_id: str,
    idempotency_key: str,
    actor: str,
) -> dict[str, int | str]:
    """Mark existing mail historical and atomically advance Gmail checkpoint."""
    if not all((org_id, connection_id, cutover_history_id, idempotency_key, actor)):
        raise ValueError("cutover scope, checkpoint, idempotency key and actor are required")

    existing = await db.scalar(
        select(CiConnectionCutover).where(
            CiConnectionCutover.org_id == org_id,
            CiConnectionCutover.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return {
            "cutover_id": existing.id,
            "cutover_at": existing.cutover_at.isoformat(),
            **existing.deleted_counts,
        }

    connection = await db.scalar(
        select(EmailConnection)
        .where(EmailConnection.id == connection_id, EmailConnection.org_id == org_id)
        .with_for_update()
    )
    if connection is None:
        raise ValueError("connection not found")

    generation = (
        await db.scalar(
            select(func.max(CiConnectionCutover.generation)).where(
                CiConnectionCutover.connection_id == connection_id
            )
        )
        or 0
    ) + 1
    cutover = CiConnectionCutover(
        org_id=org_id,
        connection_id=connection_id,
        generation=generation,
        idempotency_key=idempotency_key,
        cutover_history_id=cutover_history_id,
        status="RUNNING",
        actor=actor,
        cutover_at=utc_now(),
    )
    db.add(cutover)
    await db.flush()

    email_ids = select(InboundEmail.id).where(
        InboundEmail.org_id == org_id, InboundEmail.connection_id == connection_id
    )
    case_ids = select(ResearchCase.id).where(
        ResearchCase.org_id == org_id, ResearchCase.email_id.in_(email_ids)
    )
    results = {
        "deleted_approvals": await db.execute(
            delete(ApprovalRequest).where(ApprovalRequest.case_id.in_(case_ids))
        ),
        "deleted_deliveries": await db.execute(
            delete(DeliveryAttempt).where(DeliveryAttempt.case_id.in_(case_ids))
        ),
        "deleted_reports": await db.execute(
            delete(BriefingReport).where(BriefingReport.case_id.in_(case_ids))
        ),
        "deleted_meetings": await db.execute(
            delete(Meeting).where(Meeting.case_id.in_(case_ids))
        ),
        "deleted_sources": await db.execute(
            delete(ResearchSource).where(ResearchSource.case_id.in_(case_ids))
        ),
        "deleted_outbox_events": await db.execute(
            delete(OutboxEvent).where(
                OutboxEvent.event_type == "email.classification.requested",
                OutboxEvent.aggregate_id.in_(email_ids),
            )
        ),
        "deleted_cases": await db.execute(
            delete(ResearchCase).where(
                ResearchCase.org_id == org_id, ResearchCase.email_id.in_(email_ids)
            )
        ),
        "deleted_notifications": await db.execute(
            delete(CiNotification).where(
                CiNotification.org_id == org_id, CiNotification.email_id.in_(email_ids)
            )
        ),
    }
    marked = await db.execute(
        update(InboundEmail)
        .where(InboundEmail.org_id == org_id, InboundEmail.connection_id == connection_id)
        .values(
            classification="historical_skipped",
            classification_started_at=None,
            classification_confidence=1.0,
            classification_reason=f"clean cutover generation {generation}",
            routing_status="historical_skipped",
        )
    )
    counts = {key: int(value.rowcount or 0) for key, value in results.items()}
    counts["marked_emails"] = int(marked.rowcount or 0)
    connection.gmail_history_id = cutover_history_id
    connection.sync_cursor = None
    connection.last_sync_at = utc_now()
    cutover.status = "COMPLETED"
    cutover.deleted_counts = counts
    await db.commit()
    return {"cutover_id": cutover.id, "cutover_at": cutover.cutover_at.isoformat(), **counts}
