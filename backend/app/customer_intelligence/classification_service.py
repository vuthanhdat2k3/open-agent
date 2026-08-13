from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.observability.metrics import ci_cases_ingested_total
from app.customer_intelligence.agent_classifier import classify_with_agent
from app.customer_intelligence.contracts import EmailAttachmentMeta, NormalizedEmail
from app.customer_intelligence.delivery import request_case_approval
from app.customer_intelligence.ingest import notification_preview
from app.db.base import utc_now
from app.models.customer_intelligence import CiNotification, InboundEmail, ResearchCase
from app.repositories.outbox import OutboxRepository


def _normalized(email: InboundEmail) -> NormalizedEmail:
    return NormalizedEmail(
        provider=email.provider,
        provider_message_id=email.provider_message_id,
        thread_id=email.thread_id,
        sender_name=email.sender_name,
        sender_email=email.sender_email,
        sender_domain=email.sender_domain,
        recipients=list(email.recipients or []),
        subject=email.subject,
        body_text=email.body_text,
        body_html=email.body_html,
        attachments=[EmailAttachmentMeta(**item) for item in (email.attachments or [])],
        received_at=email.received_at,
        injection_flags=list(email.injection_flags or []),
        content_hash=email.content_hash,
    )


async def classify_and_route_email(
    db: AsyncSession,
    *,
    org_id: str,
    email_id: str,
    expected_content_hash: str | None = None,
    correlation_id: str | None = None,
    trigger: str = "webhook",
) -> dict[str, str | None]:
    now = utc_now()
    claim = await db.execute(
        update(InboundEmail)
        .where(
            InboundEmail.id == email_id,
            InboundEmail.org_id == org_id,
            *(
                [InboundEmail.content_hash == expected_content_hash]
                if expected_content_hash
                else []
            ),
            or_(
                InboundEmail.classification.in_({"pending", "queued"}),
                (
                    (InboundEmail.classification == "classifying")
                    & (
                        InboundEmail.classification_started_at
                        < now - timedelta(minutes=5)
                    )
                ),
            ),
        )
        .values(classification="classifying", classification_started_at=now)
        .returning(InboundEmail.id)
    )
    if claim.scalar_one_or_none() is None:
        email = await db.get(InboundEmail, email_id)
        if email is None or email.org_id != org_id:
            return {"status": "missing", "case_id": None}
        if expected_content_hash and email.content_hash != expected_content_hash:
            return {"status": "stale", "case_id": None}
        return {"status": "already_processed", "case_id": None}
    await db.commit()
    email = await db.get(InboundEmail, email_id)
    if email is None:
        return {"status": "missing", "case_id": None}

    result = await classify_with_agent(db, org_id, _normalized(email))
    settings = get_settings()
    email.classification = result.label
    email.classification_started_at = None
    email.classification_confidence = result.confidence
    email.classification_reason = result.reason
    email.classification_json = {
        "schema_version": "email-classification-result.v1",
        "label": result.label,
        "intents": list(result.intents),
        "company_name": result.company_name,
        "company_domain": result.company_domain,
        "company_confidence": result.company_confidence,
        "meeting_confidence": result.meeting_confidence,
        "summary": result.summary,
        "calendar": result.calendar_payload,
        "guard_flags": list(email.injection_flags or []),
    }

    ignored = {"spam", "marketing", "newsletter", "system", "transactional"}
    if result.label in ignored:
        email.routing_status = "ignored"
        await db.commit()
        return {"status": "ignored", "case_id": None}

    if result.label in {"security_risk", "uncertain"}:
        email.routing_status = "quarantined" if result.label == "security_risk" else "needs_review"
        if email.created_by_user_id:
            db.add(
                CiNotification(
                    org_id=org_id,
                    user_id=email.created_by_user_id,
                    email_id=email.id,
                    notification_type="email_review_required",
                    title=f"Email needs review from {email.sender_email}",
                    body=notification_preview(email.subject, result.summary or email.body_text),
                )
            )
        await db.commit()
        return {"status": email.routing_status, "case_id": None}

    customer_route = (
        result.label in {"customer", "partner"}
        and result.confidence >= settings.ci_classifier_accept_confidence
        and result.company_confidence >= settings.ci_classifier_company_confidence
        and bool(result.company_name or result.company_domain)
    )
    calendar_route = (
        result.label == "calendar"
        and result.confidence >= settings.ci_classifier_accept_confidence
        and result.meeting_confidence >= settings.ci_classifier_meeting_confidence
        and result.calendar_payload is not None
    )
    if not customer_route and not calendar_route:
        email.routing_status = "notified"
        if email.created_by_user_id:
            db.add(
                CiNotification(
                    org_id=org_id,
                    user_id=email.created_by_user_id,
                    email_id=email.id,
                    notification_type="email_received",
                    title=f"New email from {email.sender_email}",
                    body=notification_preview(email.subject, result.summary or email.body_text),
                )
            )
        await db.commit()
        return {"status": "notified", "case_id": None}

    case = ResearchCase(
        org_id=org_id,
        email_id=email.id,
        connection_id=email.connection_id,
        trigger="calendar" if calendar_route else trigger,
        status="ACTION_PROPOSED" if calendar_route else "INGESTED",
        company_name=result.company_name,
        company_domain=result.company_domain,
        confidence=result.confidence,
        created_by_user_id=email.created_by_user_id,
    )
    db.add(case)
    email.routing_status = "routed"
    await db.flush()
    if calendar_route:
        payload = {
            **(result.calendar_payload or {}),
            "summary": email.subject[:500] or "Meeting from email",
            "description": f"Created from email {email.provider_message_id}",
        }
        await db.commit()
        await request_case_approval(
            db,
            org_id=org_id,
            case_id=case.id,
            action="calendar_create_event",
            payload=payload,
            requested_by=email.created_by_user_id,
        )
    else:
        await OutboxRepository(db).add_event(
            event_type="ci.research.requested",
            aggregate_type="ci_case",
            aggregate_id=case.id,
            org_id=org_id,
            user_id=email.created_by_user_id,
            correlation_id=correlation_id,
            payload={"case_id": case.id},
            dedupe_key=f"ci-research:{case.id}",
        )
        await db.commit()
    ci_cases_ingested_total.labels(trigger=trigger).inc()
    return {"status": "routed", "case_id": case.id}
