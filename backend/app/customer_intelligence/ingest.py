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
from app.customer_intelligence.agent_classifier import classify_with_agent
from app.customer_intelligence.contracts import NormalizedEmail
from app.customer_intelligence.mcp import CustomerIntelligenceMcpError
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


def notification_preview(subject: str, body: str, *, max_chars: int = 600) -> str:
    """Create a bounded plain-text preview; raw unbounded email never enters UI notification."""
    compact = " ".join((body or "").split())
    preview = compact[:max_chars].rstrip()
    if len(compact) > max_chars:
        preview += "…"
    return f"{(subject or '(no subject)')[:320]}\n{preview}" if preview else (subject or "(no subject)")[:320]


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
    history_id: str | None = None,
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
            history_id=history_id,
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
    history_id: str | None = None,
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

    # ``gmail_history_id`` is the only durable sync checkpoint. A Gmail
    # messages.list nextPageToken is scoped to one bounded list operation and
    # must never be resumed by a later reconciliation tick.
    bootstrap_state = conn.sync_cursor if isinstance(conn.sync_cursor, dict) else {}
    start_history_id = conn.gmail_history_id
    history_sync = bool(start_history_id)
    bootstrap_checkpoint: str | None = None
    if not history_sync:
        bootstrap_checkpoint = str(bootstrap_state.get("history_id") or "").strip() or await provider.get_history_checkpoint()
    synced = 0
    deduplicated = 0
    new_cases = 0
    new_case_ids: list[str] = []
    warnings: list[str] = []
    last_cursor: str | None = str(bootstrap_state.get("page_token") or "").strip() or None
    latest_history_id = start_history_id or bootstrap_checkpoint
    pages = 0

    while True:
        try:
            if history_sync:
                page = await provider.list_history(
                    start_history_id=start_history_id or "",
                    page_token=last_cursor,
                    max_results=min(max_messages, 100),
                )
            else:
                page = await provider.list_new(cursor=last_cursor, max_results=max_messages)
        except CustomerIntelligenceMcpError as exc:
            # Gmail history is retained for a limited period. Recovery is a
            # bounded bootstrap from a fresh checkpoint, never an unbounded
            # inbox scan and never a retry loop on the expired cursor.
            if history_sync and "history_expired" in str(exc):
                history_sync = False
                start_history_id = None
                bootstrap_checkpoint = await provider.get_history_checkpoint()
                latest_history_id = bootstrap_checkpoint
                last_cursor = None
                pages = 0
                warnings.append("Gmail history checkpoint expired; performed bounded recovery sync")
                continue
            raise
        pages += 1
        last_cursor = page.new_cursor
        latest_history_id = page.history_id or latest_history_id
        for email in page.messages:
            existing = await email_repo.find_by_provider_message_id(
                org_id, email.provider, email.provider_message_id
            )
            if existing is not None:
                deduplicated += 1
                continue
            # Dedupe before any model call: push/reconciliation overlap must
            # cost one classification, not one call per delivery source.
            email.injection_flags = scan_for_prompt_injection(email.body_text or "")
            classification = await classify_with_agent(db, org_id, email)
            email.content_hash = email_content_hash(email)
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
                classification_json={
                    "label": classification.label,
                    "intents": list(classification.intents),
                    "company_name": classification.company_name,
                    "company_domain": classification.company_domain,
                    "company_confidence": classification.company_confidence,
                    "meeting_confidence": classification.meeting_confidence,
                    "summary": classification.summary,
                },
                routing_status=(
                    "ignored" if classification.label in {"spam", "marketing", "newsletter", "system", "transactional"}
                    else "quarantined" if classification.label in {"security_risk", "uncertain"}
                    else "routed"
                ),
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
            if classification.label in {"spam", "marketing", "newsletter", "system", "transactional"}:
                warnings.append(f"email {email.provider_message_id}: spam ignored")
                continue
            if classification.label in {"security_risk", "uncertain"}:
                reason = (
                    "potential prompt injection flagged"
                    if classification.label == "security_risk" and email.injection_flags
                    else "classification requires review"
                )
                warnings.append(
                    f"email {email.provider_message_id}: {reason}"
                )
                if conn.created_by_user_id:
                    db.add(CiNotification(
                        org_id=org_id,
                        user_id=conn.created_by_user_id,
                        email_id=row.id,
                        notification_type="email_review_required",
                        title=f"Email needs review from {email.sender_email}",
                        body=notification_preview(email.subject, classification.summary or email.body_text),
                    ))
                    await db.commit()
                continue
            settings = get_settings()
            is_customer_route = (
                classification.label in {"customer", "partner"}
                and classification.confidence >= settings.ci_classifier_accept_confidence
                and classification.company_confidence >= settings.ci_classifier_company_confidence
                and bool(classification.company_name or classification.company_domain)
            )
            is_calendar_route = (
                classification.label == "calendar"
                and classification.confidence >= settings.ci_classifier_accept_confidence
                and classification.meeting_confidence >= settings.ci_classifier_meeting_confidence
            )
            if not is_customer_route and not is_calendar_route:
                if conn.created_by_user_id:
                    db.add(
                        CiNotification(
                            org_id=org_id,
                            user_id=conn.created_by_user_id,
                            email_id=row.id,
                            notification_type="email_received",
                            title=f"New email from {email.sender_email}",
                            body=notification_preview(email.subject, classification.summary or email.body_text),
                        )
                    )
                    await db.commit()
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
                company_name=classification.company_name,
                company_domain=classification.company_domain,
                confidence=classification.confidence,
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
                        body=notification_preview(email.subject, email.body_text),
                    )
                )
                await db.commit()
            new_cases += 1
            new_case_ids.append(case.id)
        # Bootstrap is intentionally bounded. History pagination is also
        # bounded per invocation so a mailbox burst cannot monopolize a
        # worker; the next notification/reconciliation resumes from the
        # durable checkpoint.
        page_limit = 5 if not history_sync else 20
        if not page.has_more or pages >= page_limit:
            break
        if last_cursor is None:
            break

    await conn_repo.update(
        conn,
        {
            # A page token is allowed only while a bounded bootstrap is still
            # draining. It is never used for incremental reconciliation after
            # gmail_history_id has been established.
            "sync_cursor": (
                {"mode": "bootstrap", "history_id": bootstrap_checkpoint, "page_token": last_cursor}
                if not history_sync and page.has_more and last_cursor
                else None
            ),
            "gmail_history_id": latest_history_id if history_sync or not page.has_more else None,
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
        "history_id": latest_history_id,
        "mode": "history" if history_sync else "bootstrap",
        "warnings": warnings,
    }
