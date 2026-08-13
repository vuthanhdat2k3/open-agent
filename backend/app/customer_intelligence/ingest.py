from __future__ import annotations

import hashlib
import time
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.observability.audit import log_action
from app.core.observability.metrics import (
    ci_cases_ingested_total,
    ci_sync_duration_seconds,
    ci_syncs_total,
)
from app.core.workflow.queue import enqueue_ci_research
from app.customer_intelligence.classifier import classify_email
from app.customer_intelligence.contracts import NormalizedEmail, SyncPage
from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.email import bind_email_provider, get_email_provider
from app.customer_intelligence.security import scan_for_prompt_injection
from app.db.base import gen_id, utc_now
from app.models.customer_intelligence import (
    CiNotification,
    InboundEmail,
    ResearchCase,
)
from app.repositories.customer_intelligence import (
    EmailConnectionRepository,
    InboundEmailRepository,
    ResearchCaseRepository,
)

logger = structlog.get_logger(__name__)


class IngestionError(Exception):
    pass


def email_content_hash(email: NormalizedEmail) -> str:
    canonical = "|".join(
        [
            email.provider_message_id,
            email.sender_email.lower(),
            email.subject,
            email.body_text.strip()[:500],
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def sync_connection(
    db: AsyncSession,
    *,
    org_id: str,
    connection_id: str,
    trigger: str = "manual",
    max_messages: int = 20,
    actor_user_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Sync a connection and record bounded CI metrics.

    This is the single writer for the customer-intelligence metrics: both the
    manual sync route and the scheduler call it, so all sync attempts count
    exactly once. Labels stay bounded (result / trigger) and never include the
    tenant or connection id.

    A correlation id ties the metrics, logs and the ``ci.connection.synced``
    audit row together across the scheduler and API entry points so an operator
    can trace one sync attempt end to end.
    """
    correlation_id = correlation_id or gen_id()
    started = time.monotonic()
    try:
        result = await _sync_connection_impl(
            db,
            org_id=org_id,
            connection_id=connection_id,
            trigger=trigger,
            max_messages=max_messages,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    except Exception:
        ci_syncs_total.labels(result="error").inc()
        ci_sync_duration_seconds.observe(time.monotonic() - started)
        raise
    ci_syncs_total.labels(result="success").inc()
    ci_cases_ingested_total.labels(trigger=trigger).inc(result["new_cases"])
    ci_sync_duration_seconds.observe(time.monotonic() - started)
    result["correlation_id"] = correlation_id
    return result


async def _sync_connection_impl(
    db: AsyncSession,
    *,
    org_id: str,
    connection_id: str,
    trigger: str = "manual",
    max_messages: int = 20,
    actor_user_id: str | None = None,
    correlation_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    conn_repo = EmailConnectionRepository(db)
    email_repo = InboundEmailRepository(db)
    case_repo = ResearchCaseRepository(db)

    conn = await conn_repo.get(org_id, connection_id)
    if conn is None:
        raise IngestionError("connection not found")
    if conn.status != "connected":
        raise IngestionError("connection is not connected")
    if not conn.credentials_enc:
        raise IngestionError("connection has no credentials")

    credentials = await load_fresh_credentials(db, conn)
    provider = bind_email_provider(get_email_provider(conn.provider), credentials)

    cursor = (conn.sync_cursor or {}).get("cursor")
    synced = 0
    deduplicated = 0
    new_cases = 0
    new_case_ids: list[str] = []
    warnings: list[str] = []
    last_cursor = cursor
    pages = 0

    while True:
        page: SyncPage = await provider.list_new(cursor=last_cursor, max_results=max_messages)
        pages += 1
        last_cursor = page.new_cursor
        for email in page.messages:
            email.injection_flags = scan_for_prompt_injection(email.body_text or "")
            classification = classify_email(email)
            email.content_hash = email_content_hash(email)
            existing = await email_repo.find_by_provider_message_id(
                org_id, email.provider, email.provider_message_id
            )
            if existing is not None:
                deduplicated += 1
                continue
            row = InboundEmail(
                org_id=org_id,
                connection_id=connection_id,
                provider=email.provider,
                provider_message_id=email.provider_message_id,
                thread_id=email.thread_id,
                sender_name=email.sender_name,
                sender_email=email.sender_email,
                sender_domain=email.sender_domain,
                recipients=email.recipients,
                subject=email.subject,
                body_text=email.body_text,
                body_html=email.body_html,
                attachments=[a.__dict__ for a in email.attachments],
                received_at=email.received_at,
                content_hash=email.content_hash,
                injection_flags=email.injection_flags,
                classification=classification.label,
                classification_confidence=classification.confidence,
                classification_reason=classification.reason,
                routing_status="ignored" if classification.label == "spam" else "quarantined" if classification.label == "security_risk" else "routed",
                created_by_user_id=conn.created_by_user_id,
            )
            try:
                await email_repo.create(row)
            except IntegrityError:
                await db.rollback()
                existing = await email_repo.find_by_provider_message_id(
                    org_id, email.provider, email.provider_message_id
                )
                if existing is not None:
                    deduplicated += 1
                    continue
                raise
            synced += 1
            if classification.label == "spam":
                warnings.append(f"email {email.provider_message_id}: spam ignored")
                continue
            if classification.label == "security_risk":
                warnings.append(
                    f"email {email.provider_message_id}: potential prompt injection flagged"
                )
                continue
            if len(email.attachments) > 0 and email.attachments[0].size_bytes > settings.ci_max_attachment_bytes:
                warnings.append(
                    f"email {email.provider_message_id}: attachment over size limit, content skipped"
                )
            case = ResearchCase(
                org_id=org_id,
                email_id=row.id,
                connection_id=connection_id,
                trigger=trigger,
                status="INGESTED",
                created_by_user_id=conn.created_by_user_id,
            )
            await case_repo.create(case)
            if conn.created_by_user_id:
                db.add(
                    CiNotification(
                        org_id=org_id,
                        user_id=conn.created_by_user_id,
                        email_id=row.id,
                        notification_type="email_received",
                        title=f"New email from {email.sender_email}",
                        body=(email.subject or "(no subject)")[:320],
                    )
                )
                await db.commit()
            new_cases += 1
            new_case_ids.append(case.id)
        if not page.has_more or pages >= 20:
            break
        if last_cursor is None:
            break

    await conn_repo.update(
        conn,
        {
            "sync_cursor": {"cursor": last_cursor} if last_cursor else None,
            "last_sync_at": utc_now(),
        },
    )
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=actor_user_id,
        action="ci.connection.synced",
        resource_type="ci_connection",
        resource_id=connection_id,
        metadata={
            "trigger": trigger,
            "synced": synced,
            "deduplicated": deduplicated,
            "new_cases": new_cases,
            "pages": pages,
            "correlation_id": correlation_id,
        },
    )
    # Enqueue research after every case is durably committed: a case is
    # created (and thus already persisted) the moment case_repo.create()
    # returns, so a job for an earlier case in this sync must not be lost if
    # a later email in the same page raises. Enqueue failures (Redis down)
    # are logged, not raised - the sync itself already succeeded and must
    # not be reported as failed just because the follow-up job could not be
    # queued; the case stays INGESTED and can still be researched manually
    # or picked up by a future retry sweep.
    for new_case_id in new_case_ids:
        try:
            await enqueue_ci_research(org_id, new_case_id)
        except Exception as exc:  # noqa: BLE001 - queue outage must not fail the sync.
            await logger.aerror(
                "ci_auto_research_enqueue_failed",
                org_id=org_id,
                case_id=new_case_id,
                error=str(exc),
            )
    return {
        "connection_id": connection_id,
        "synced": synced,
        "deduplicated": deduplicated,
        "new_cases": new_cases,
        "cursor": last_cursor,
        "warnings": warnings,
    }
