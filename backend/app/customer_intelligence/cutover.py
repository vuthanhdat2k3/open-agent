"""Safe clean-cutover helpers for the agent classification rollout.

The command intentionally preserves raw inbound emails as historical records,
but removes derived intelligence so old mail cannot be re-routed by the new
classifier. New ingestion starts from the connection checkpoint after the
cutover marker is written.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import (
    BriefingReport,
    CiNotification,
    DeliveryAttempt,
    InboundEmail,
    Meeting,
    ResearchCase,
    ResearchSource,
)


async def clean_cutover(
    db: AsyncSession,
    *,
    org_id: str | None = None,
    connection_id: str | None = None,
    actor: str = "operator",
) -> dict[str, int | str]:
    """Delete derived CI data and mark existing mail as historical/processed.

    This function is deliberately not called during application startup. It is
    an explicit operational command, suitable for a one-time deployment step.
    """
    filters = []
    if org_id:
        filters.append(InboundEmail.org_id == org_id)
    if connection_id:
        filters.append(InboundEmail.connection_id == connection_id)

    email_ids = select(InboundEmail.id).where(*filters) if filters else select(InboundEmail.id)
    case_ids = select(ResearchCase.id).where(ResearchCase.email_id.in_(email_ids))

    # Approval and delivery records reference cases; remove them before the
    # case rows for databases where FK cascade is not enabled.
    deleted_approvals = await db.execute(delete(ApprovalRequest).where(ApprovalRequest.case_id.in_(case_ids)))
    deleted_deliveries = await db.execute(delete(DeliveryAttempt).where(DeliveryAttempt.case_id.in_(case_ids)))
    deleted_reports = await db.execute(delete(BriefingReport).where(BriefingReport.case_id.in_(case_ids)))
    deleted_meetings = await db.execute(delete(Meeting).where(Meeting.case_id.in_(case_ids)))
    deleted_sources = await db.execute(delete(ResearchSource).where(ResearchSource.case_id.in_(case_ids)))
    deleted_cases = await db.execute(delete(ResearchCase).where(ResearchCase.email_id.in_(email_ids)))
    deleted_notifications = await db.execute(delete(CiNotification).where(CiNotification.email_id.in_(email_ids)))
    marked = await db.execute(
        update(InboundEmail)
        .where(*filters)
        .values(
            classification="historical_skipped",
            classification_confidence=1.0,
            classification_reason=f"clean cutover by {actor}",
            routing_status="historical_skipped",
        )
    )
    now = datetime.now(timezone.utc).isoformat()
    await db.commit()
    return {
        "cutover_at": now,
        "marked_emails": int(marked.rowcount or 0),
        "deleted_cases": int(deleted_cases.rowcount or 0),
        "deleted_reports": int(deleted_reports.rowcount or 0),
        "deleted_sources": int(deleted_sources.rowcount or 0),
        "deleted_meetings": int(deleted_meetings.rowcount or 0),
        "deleted_notifications": int(deleted_notifications.rowcount or 0),
        "deleted_approvals": int(deleted_approvals.rowcount or 0),
        "deleted_deliveries": int(deleted_deliveries.rowcount or 0),
    }
