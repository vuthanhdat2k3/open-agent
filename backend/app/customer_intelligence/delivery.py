"""Approval-gated, idempotent side effects for Customer Intelligence.

A research case produces a briefing; turning that briefing into an external
side effect (e.g. sending the briefing email to the account) is gated behind a
human approval. This module owns that gate:

* ``request_case_approval`` creates an ``ApprovalRequest`` linked to a case
  (``case_id``), stamped with an expiry and a payload hash so the reviewer and
  the executor agree on *exactly* what will be sent. Opening the same action on
  the same case twice returns the existing pending request (idempotent) instead
  of piling up duplicates.
* ``decide_case_approval`` resolves a request: rejected -> case REJECTED;
  expired -> case EXPIRED; approved -> run the side effect via
  ``run_delivery`` and move the case through APPROVED/EXECUTING/COMPLETED.
* ``run_delivery`` performs the side effect once and only once
  (``DeliveryAttempt`` is unique per ``org_id``+``idempotency_key``).

Only ``send_email`` is currently supported. ``save_knowledge`` has no backing
sink yet, so it is rejected with an explicit error rather than a fabricated
success — consistent with the "never invent data" rule.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from email.utils import parseaddr
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.observability.audit import log_action
from app.core.observability.metrics import ci_approval_age_seconds
from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.email import (
    bind_email_provider,
    get_email_provider,
)
from app.db.base import utc_now
from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import (
    DeliveryAttempt,
    ResearchCase,
)
from app.repositories.customer_intelligence import (
    DeliveryAttemptRepository,
    EmailConnectionRepository,
    ResearchCaseRepository,
)


class DeliveryError(Exception):
    """Raised for a side effect that cannot be dispatched."""


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


async def _pending_for_case(
    db: AsyncSession, *, org_id: str, case_id: str, action: str
) -> ApprovalRequest | None:
    """Return the first pending ApprovalRequest for (org, case, action) if any."""
    res = await db.execute(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.org_id == org_id,
            ApprovalRequest.case_id == case_id,
            ApprovalRequest.status == "pending",
            ApprovalRequest.tool_name == action,
        )
        .order_by(ApprovalRequest.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def request_case_approval(
    db: AsyncSession,
    *,
    org_id: str,
    case_id: str,
    action: str,
    payload: dict[str, Any],
    requested_by: str | None = None,
) -> ApprovalRequest:
    """Open (or return the existing open) approval for a delivery action.

    The case must be REPORT_READY or ACTION_PROPOSED. The request
    carries a deterministic ``idempotency_key`` so re-proposing the same action
    never duplicates the gate.
    """
    settings = get_settings()
    case_repo = ResearchCaseRepository(db)
    case = await case_repo.get(org_id, case_id)
    if case is None:
        raise DeliveryError("case not found")

    # Idempotency first: re-proposing the same action while a pending approval
    # for it exists returns the existing request regardless of the case's
    # current status (opening the gate never duplicates it).
    existing = await _pending_for_case(db, org_id=org_id, case_id=case_id, action=action)
    if existing is not None:
        return existing

    if case.status not in {"REPORT_READY", "ACTION_PROPOSED"}:
        raise DeliveryError(
            f"case is not ready for approval (status={case.status}); has it been researched?"
        )

    ph = _payload_hash(payload)
    idempotency_key = f"ci:{case_id}:{action}"
    approval = ApprovalRequest(
        org_id=org_id,
        run_type="ci.delivery",
        run_id=case_id,
        tool_name=action,
        node_id=None,
        args_snapshot=payload,
        requested_by=requested_by,
        status="pending",
        case_id=case_id,
        expires_at=utc_now() + timedelta(hours=settings.ci_approval_expiry_hours),
        payload_hash=ph,
        idempotency_key=idempotency_key,
    )
    db.add(approval)
    try:
        await case_repo.transition(case, "AWAITING_APPROVAL")
    except IntegrityError:
        await db.rollback()
        existing = await _pending_for_case(db, org_id=org_id, case_id=case_id, action=action)
        if existing is not None:
            return existing
        raise DeliveryError("could not create approval")
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=requested_by,
        action="ci.approval.requested",
        resource_type="ci_case",
        resource_id=case_id,
        metadata={"action": action, "payload_hash": ph, "idempotency_key": idempotency_key},
    )
    await db.refresh(approval)
    return approval


async def _expire_case(db: AsyncSession, case: ResearchCase) -> None:
    cases = ResearchCaseRepository(db)
    await cases.transition(case, "EXPIRED")


async def decide_case_approval(
    db: AsyncSession,
    *,
    org_id: str,
    approval_id: str,
    decision: str,
    decided_by: str | None = None,
    reason: str = "",
    expected_case_id: str | None = None,
) -> ApprovalRequest:
    """Decide a pending case approval.

    ``decision`` is ``approved`` | ``rejected``. Requests whose ``expires_at``
    has passed are marked EXPIRED (decision ignored). Approving dispatches the
    side effect through ``run_delivery`` and drives the case through
    APPROVED -> EXECUTING -> COMPLETED (or RETRYING on failure).
    """
    if decision not in {"approved", "rejected"}:
        raise DeliveryError("decision must be 'approved' or 'rejected'")
    if not org_id or not approval_id:
        raise TypeError("org_id and approval_id are required")

    res = await db.execute(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.org_id == org_id,
        )
        .with_for_update()
    )
    approval = res.scalar_one_or_none()
    if approval is None:
        raise DeliveryError("approval request not found")
    if expected_case_id is not None and approval.case_id != expected_case_id:
        raise DeliveryError("approval does not belong to case")
    if approval.status != "pending":
        raise DeliveryError("approval request is already decided")

    case = await ResearchCaseRepository(db).get(org_id, approval.case_id or "")
    if case is None:
        raise DeliveryError("case not found")

    if approval.payload_hash and _payload_hash(approval.args_snapshot or {}) != approval.payload_hash:
        raise DeliveryError("approval payload has changed")

    now = utc_now()
    age_seconds = 0.0
    if approval.created_at is not None:
        age_seconds = max(0.0, (now - approval.created_at).total_seconds())
    if approval.expires_at is not None and approval.expires_at <= now:
        approval.status = "expired"
        approval.decided_by = decided_by
        approval.decided_at = now
        approval.reason = reason or "approval expired"
        await db.commit()
        await _expire_case(db, case)
        ci_approval_age_seconds.labels(decision="expired").observe(age_seconds)
        await log_action(
            db,
            org_id=org_id,
            actor_user_id=decided_by,
            action="ci.approval.expired",
            resource_type="ci_case",
            resource_id=case.id,
            metadata={
                "approval_id": approval.id,
                "approval_age_seconds": age_seconds,
            },
        )
        return approval

    approval.status = decision
    approval.decided_by = decided_by
    approval.decided_at = now
    approval.reason = reason
    await db.commit()

    if decision == "rejected":
        cases = ResearchCaseRepository(db)
        await cases.transition(case, "REJECTED")
        ci_approval_age_seconds.labels(decision="rejected").observe(age_seconds)
        await log_action(
            db,
            org_id=org_id,
            actor_user_id=decided_by,
            action="ci.approval.rejected",
            resource_type="ci_case",
            resource_id=case.id,
            metadata={
                "approval_id": approval.id,
                "reason": reason,
                "approval_age_seconds": age_seconds,
            },
        )
        return approval

    # approved -> run the side effect
    cases = ResearchCaseRepository(db)
    await cases.transition(case, "APPROVED")
    await cases.transition(case, "EXECUTING")
    try:
        attempt = await run_delivery(
            db,
            org_id=org_id,
            case=case,
            approval=approval,
            actor_user_id=decided_by,
        )
    except Exception as exc:  # noqa: BLE001 - provider errors must enter retry state.
        error = exc if isinstance(exc, DeliveryError) else DeliveryError("delivery provider failed")
        await cases.transition(case, "RETRYING")
        await log_action(
            db,
            org_id=org_id,
            actor_user_id=decided_by,
            action="ci.approval.approved_execution_failed",
            resource_type="ci_case",
            resource_id=case.id,
            metadata={"approval_id": approval.id, "error": str(error)},
        )
        raise error from exc
    await cases.transition(case, "COMPLETED")
    ci_approval_age_seconds.labels(decision="approved").observe(age_seconds)
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=decided_by,
        action="ci.approval.approved",
        resource_type="ci_case",
        resource_id=case.id,
        metadata={
            "approval_id": approval.id,
            "action": approval.tool_name,
            "attempt_id": attempt.id,
            "provider_send_id": attempt.provider_send_id,
            "approval_age_seconds": age_seconds,
        },
    )
    return approval


async def run_delivery(
    db: AsyncSession,
    *,
    org_id: str,
    case: ResearchCase,
    approval: ApprovalRequest,
    actor_user_id: str | None = None,
) -> DeliveryAttempt:
    """Execute an approved side effect exactly once.

    Idempotency: a DeliveryAttempt keyed by ``org_id``+``idempotency_key`` is
    the source of truth. If one already reached ``delivered``, it is returned
    unchanged — a crashed approval/worker replay must not resend.
    """
    action = approval.tool_name or ""
    attempts = DeliveryAttemptRepository(db)
    idempotency_key = approval.idempotency_key or f"ci:{case.id}:{action}"

    existing = await attempts.get_by_idempotency_key(org_id, idempotency_key)
    if existing is not None and existing.status == "delivered":
        await log_action(
            db,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="ci.delivery.replayed",
            resource_type="ci_delivery",
            resource_id=existing.id,
            metadata={"idempotency_key": idempotency_key},
        )
        return existing
    if existing is not None and existing.status == "pending":
        raise DeliveryError("delivery attempt is pending; reconcile provider before retry")

    if action == "send_email":
        return await _deliver_email(
            db,
            org_id=org_id,
            case=case,
            approval=approval,
            idempotency_key=idempotency_key,
            existing=existing,
            actor_user_id=actor_user_id,
        )
    if action == "calendar_create_event":
        return await _deliver_calendar_event(
            db,
            org_id=org_id,
            case=case,
            approval=approval,
            idempotency_key=idempotency_key,
            existing=existing,
        )
    if action == "save_knowledge":
        raise DeliveryError(
            "save_knowledge has no backing sink yet; only send_email is available"
        )
    raise DeliveryError(f"unsupported delivery action: {action}")


async def _deliver_calendar_event(
    db: AsyncSession,
    *,
    org_id: str,
    case: ResearchCase,
    approval: ApprovalRequest,
    idempotency_key: str,
    existing: DeliveryAttempt | None = None,
) -> DeliveryAttempt:
    payload: dict[str, Any] = approval.args_snapshot or {}
    required = {"summary", "start", "end"}
    if not required.issubset(payload):
        raise DeliveryError("calendar_create_event requires summary, start and end")
    from app.customer_intelligence.providers.research import (
        bind_calendar_provider,
        get_calendar_provider,
    )
    from app.repositories.customer_intelligence import CalendarConnectionRepository

    connection = await CalendarConnectionRepository(db).get_connected(
        org_id, user_id=case.created_by_user_id
    )
    if connection is None or not connection.credentials_enc:
        raise DeliveryError("no connected calendar account")
    if existing is not None and existing.status == "pending":
        raise DeliveryError("calendar creation is pending; reconcile provider before retry")
    credentials = await load_fresh_credentials(db, connection)
    provider = bind_calendar_provider(get_calendar_provider(), credentials)
    attempts = DeliveryAttemptRepository(db)
    attempt = existing or DeliveryAttempt(
        org_id=org_id,
        case_id=case.id,
        action="calendar_create_event",
        payload_hash=approval.payload_hash or "",
        idempotency_key=idempotency_key,
        status="pending",
    )
    if existing is None:
        await attempts.create(attempt)
    try:
        result = await provider.create_event(**payload)
    except Exception as exc:  # noqa: BLE001 - pending prevents blind replay.
        if attempt.id:
            await attempts.touch(attempt, error="calendar provider create failed", status="pending")
        raise DeliveryError("calendar event creation failed") from exc
    event_id = str(result.get("event_id") or result.get("id") or "")
    if not event_id:
        raise DeliveryError("calendar provider returned no event id")
    return await attempts.touch(
        attempt,
        provider_send_id=event_id,
        status="delivered",
        error=None,
    )


async def _deliver_email(
    db: AsyncSession,
    *,
    org_id: str,
    case: ResearchCase,
    approval: ApprovalRequest,
    idempotency_key: str,
    existing: DeliveryAttempt | None = None,
    actor_user_id: str | None = None,
) -> DeliveryAttempt:
    payload: dict[str, Any] = approval.args_snapshot or {}
    to = payload.get("to")
    subject = payload.get("subject")
    body = payload.get("body")
    if not to or not subject or body is None:
        raise DeliveryError("send_email requires to, subject and body")

    if "," in to or ";" in to or parseaddr(to)[1] != to.strip() or "@" not in parseaddr(to)[1]:
        raise DeliveryError("send_email requires one valid recipient")

    conn = await EmailConnectionRepository(db).get(org_id, case.connection_id or "")
    if conn is None or not conn.credentials_enc:
        raise DeliveryError("no connected email account to send from")

    creds = await load_fresh_credentials(db, conn)
    provider = bind_email_provider(get_email_provider(conn.provider), creds)

    attempts = DeliveryAttemptRepository(db)
    attempt = existing
    draft_id = attempt.provider_draft_id if attempt else None
    if not draft_id:
        try:
            draft_id = await provider.create_draft(to=to, subject=subject, body=body)
        except Exception as exc:  # noqa: BLE001 - normalize provider details.
            raise DeliveryError("email draft creation failed") from exc
        if not draft_id:
            raise DeliveryError("email provider returned an empty draft id")

    if attempt is None:
        attempt = DeliveryAttempt(
            org_id=org_id,
            case_id=case.id,
            action="send_email",
            provider_id=conn.id,
            provider_draft_id=draft_id,
            payload_hash=approval.payload_hash or "",
            idempotency_key=idempotency_key,
            status="pending",
        )
        await attempts.create(attempt)
    else:
        await attempts.touch(
            attempt,
            provider_id=conn.id,
            provider_draft_id=draft_id,
            payload_hash=approval.payload_hash or "",
            retry_count=attempt.retry_count + 1,
            error=None,
        )

    try:
        send_id = await provider.send(draft_id=draft_id, idempotency_key=idempotency_key)
    except Exception as exc:  # noqa: BLE001 - preserve pending attempt for reconciliation.
        await attempts.touch(attempt, error="email provider send failed", status="pending")
        raise DeliveryError("email provider send failed") from exc

    attempt = await attempts.touch(
        attempt,
        provider_id=conn.id,
        provider_draft_id=draft_id,
        provider_send_id=send_id,
        payload_hash=approval.payload_hash or "",
        status="delivered",
        error=None,
    )
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=actor_user_id,
        action="ci.delivery.sent" if existing is None else "ci.delivery.retried_sent",
        resource_type="ci_delivery",
        resource_id=attempt.id,
        metadata={
            "idempotency_key": idempotency_key,
            "provider_draft_id": draft_id,
            "provider_send_id": send_id,
        },
    )
    return attempt
