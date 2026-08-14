from __future__ import annotations

import hashlib
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.core.observability.metrics import (
    ci_cases_ingested_total,
    ci_sync_duration_seconds,
    ci_syncs_total,
)
from app.customer_intelligence.contracts import NormalizedEmail
from app.customer_intelligence.mcp import CustomerIntelligenceMcpError
from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.email import bind_email_provider, get_email_provider
from app.customer_intelligence.security import scan_for_prompt_injection
from app.db.base import gen_id, utc_now
from app.models.customer_intelligence import InboundEmail
from app.models.workflow_installation import WorkflowInstallation
from app.repositories.customer_intelligence import (
    EmailConnectionRepository,
    InboundEmailRepository,
)
from app.repositories.outbox import OutboxRepository


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
    conn_repo = EmailConnectionRepository(db)
    email_repo = InboundEmailRepository(db)

    conn = await conn_repo.get(org_id, connection_id)
    if conn is None:
        raise IngestionError("connection not found")
    if conn.status != "connected":
        raise IngestionError("connection is not connected")
    if not conn.credentials_enc:
        raise IngestionError("connection has no credentials")

    # Gmail sync remains durable while analysis is controlled by the user's
    # Automation Hub installation. This prevents an accidental mailbox-wide
    # LLM scan when the monitor is paused or has not been enabled yet.
    monitor_enabled = await db.scalar(
        select(WorkflowInstallation.id).where(
            WorkflowInstallation.org_id == org_id,
            WorkflowInstallation.owner_user_id == conn.created_by_user_id,
            WorkflowInstallation.template_key.in_(["gmail_monitor_and_triage", "new-customer-intelligence"]),
            WorkflowInstallation.status == "enabled",
            WorkflowInstallation.settings["connection_id"].as_string() == connection_id,
        )
    ) is not None

    credentials = await load_fresh_credentials(db, conn)
    provider = bind_email_provider(get_email_provider(conn.provider), credentials)

    # ``gmail_history_id`` is the only durable sync checkpoint. A Gmail
    # messages.list nextPageToken is scoped to one bounded list operation and
    # must never be resumed by a later reconciliation tick.
    bootstrap_state = conn.sync_cursor if isinstance(conn.sync_cursor, dict) else {}
    # A connection may still have a bounded bootstrap page token from an
    # older deployment. Once that baseline history id exists, promote it to
    # the durable incremental checkpoint immediately. Continuing the old
    # mailbox pagination first can starve newly received mail behind a large
    # inbox and violates the "process mail received after connect" contract.
    start_history_id = conn.gmail_history_id or str(bootstrap_state.get("history_id") or "").strip() or None
    history_sync = bool(start_history_id)
    bootstrap_checkpoint: str | None = None
    if not history_sync:
        bootstrap_checkpoint = str(bootstrap_state.get("history_id") or "").strip() or await provider.get_history_checkpoint()
    synced = 0
    deduplicated = 0
    new_cases = 0
    classification_queued = 0
    warnings: list[str] = []
    # A messages.list page token is never valid for Gmail History API. When
    # promoting a persisted bootstrap baseline, start history pagination from
    # the baseline itself and discard the old mailbox cursor.
    last_cursor: str | None = (
        None
        if history_sync
        else str(bootstrap_state.get("page_token") or "").strip() or None
    )
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
            email.injection_flags = scan_for_prompt_injection(email.body_text or "")
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
                classification="queued" if monitor_enabled else "monitoring_paused",
                routing_status="pending" if monitor_enabled else "monitoring_paused",
                created_by_user_id=conn.created_by_user_id,
            )
            try:
                async with db.begin_nested():
                    db.add(row)
                    await db.flush()
            except IntegrityError:
                existing = await email_repo.find_by_provider_message_id(
                    org_id, email.provider, email.provider_message_id
                )
                if existing is not None:
                    deduplicated += 1
                    continue
                raise
            if monitor_enabled:
                await OutboxRepository(db).add_event(
                    event_type="email.classification.requested",
                    aggregate_type="ci_email",
                    aggregate_id=row.id,
                    org_id=org_id,
                    user_id=conn.created_by_user_id,
                    correlation_id=correlation_id,
                    payload={
                        "email_id": row.id,
                        "content_hash": row.content_hash,
                        "trigger": trigger,
                    },
                    dedupe_key=f"email-classification:{row.id}:{row.content_hash}",
                )
            await db.commit()
            synced += 1
            if monitor_enabled:
                classification_queued += 1
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
    return {
        "connection_id": connection_id,
        "synced": synced,
        "deduplicated": deduplicated,
        "new_cases": new_cases,
        "classification_queued": classification_queued,
        "cursor": last_cursor,
        "history_id": latest_history_id,
        "mode": "history" if history_sync else "bootstrap",
        "warnings": warnings,
    }
