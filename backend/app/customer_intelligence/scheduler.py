"""M6 - Customer Intelligence scheduler.

Drives periodic per-timezone daily syncs for ``CiSchedule`` rows. The worker
calls :func:`run_due_schedules` on a short cron cadence; only schedules whose
``next_run_at`` has passed are synced, and each run advances ``last_run_at`` /
``next_run_at`` to the next wall-clock occurrence.

Timezone handling is the subtle part: models persist naive UTC (see
``app.db.base.utc_now``), so :func:`compute_next_run_at` computes the next
wall-clock occurrence in the schedule's zone and converts back to naive UTC.
DST transitions are handled naturally by ``zoneinfo``.

Metrics are emitted by :func:`app.customer_intelligence.ingest.sync_connection`
(single writer for both manual and scheduled syncs); this module only isolates
failures so one bad schedule never kills the tick.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.observability.audit import log_action
from app.core.workflow.queue import enqueue_ci_research
from app.customer_intelligence.ingest import IngestionError, sync_connection
from app.db.base import gen_id, utc_now
from app.models.customer_intelligence import CiSchedule, EmailConnection
from app.repositories.customer_intelligence import CiScheduleRepository
from app.repositories.outbox import OutboxRepository

logger = structlog.get_logger(__name__)

SCHEDULED_MAX_MESSAGES = 20


async def enqueue_gmail_maintenance_events(
    db: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Fan out reconciliation/renewal events with per-connection idempotency."""
    now = now or utc_now()
    from sqlalchemy import select

    connections = list(
        (
            await db.scalars(
                select(EmailConnection).where(
                    EmailConnection.provider == "gmail",
                    EmailConnection.status == "connected",
                )
            )
        ).all()
    )
    bucket = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    repo = OutboxRepository(db)
    reconciliations = 0
    renewals = 0
    for connection in connections:
        await repo.add_event(
            event_type="gmail.reconciliation.requested",
            aggregate_type="gmail_connection",
            aggregate_id=connection.id,
            org_id=connection.org_id,
            user_id=connection.created_by_user_id,
            payload={"connection_id": connection.id, "scheduled_for": bucket.isoformat()},
            dedupe_key=f"gmail-reconcile:{connection.id}:{bucket.isoformat()}",
        )
        reconciliations += 1
        if get_settings().gmail_pubsub_topic and (
            connection.watch_expiration_at is None
            or connection.watch_expiration_at <= now + timedelta(hours=48)
        ):
            generation = connection.watch_expiration_at.isoformat() if connection.watch_expiration_at else "initial"
            await repo.add_event(
                event_type="gmail.watch.renew.requested",
                aggregate_type="gmail_connection",
                aggregate_id=connection.id,
                org_id=connection.org_id,
                user_id=connection.created_by_user_id,
                payload={"connection_id": connection.id, "watch_generation": generation},
                dedupe_key=f"gmail-watch-renew:{connection.id}:{generation}",
            )
            renewals += 1
    await db.commit()
    return {"connections": len(connections), "reconciliation_events": reconciliations, "renewal_events": renewals}


def _coerce_zone(tz_name: str) -> ZoneInfo:
    """Resolve an IANA zone name; fall back to UTC for unknown/bad names.

    A bad ``timezone`` value must never take the whole scheduler down - the rest
    of an org's schedules should keep firing.
    """
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("UTC")


def compute_next_run_at(run_time: str, timezone_: str, now: datetime | None = None) -> datetime:
    """Next wall-clock ``run_time`` (``HH:MM``) in ``timezone_`` strictly after ``now``.

    ``now`` is naive UTC (matching the model layer) and the result is also naive
    UTC. If the run time on ``now``'s local calendar day has already passed, the
    next day's occurrence is returned (DST-aware via zoneinfo).
    """
    now = now or utc_now()
    parts = run_time.split(":")
    if len(parts) != 2:
        raise ValueError("run_time must be HH:MM")
    hour, minute = (int(part) for part in parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("run_time must be HH:MM")
    zone = _coerce_zone(timezone_)

    # Interpret naive ``now`` as UTC, then project into the target zone.
    aware_now = now.replace(tzinfo=timezone.utc).astimezone(zone)
    candidate = aware_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= aware_now:
        candidate += timedelta(days=1)
    # Back to naive UTC for persistence.
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


async def _run_due_schedules_unlocked(
    db: AsyncSession, *, now: datetime | None = None, actor_user_id: str | None = None
) -> dict[str, Any]:
    """Sync every due schedule once and advance its next run.

    Returns a summary dict for logging/testing. A failure on one schedule is
    isolated so the rest still run.
    """
    now = now or utc_now()
    repo = CiScheduleRepository(db)
    due = await repo.list_due(now)

    processed: list[str] = []
    failed: list[tuple[str, str]] = []

    for schedule in due:
        try:
            await _run_one(db, schedule, now=now, actor_user_id=actor_user_id)
        except Exception as exc:  # noqa: BLE001 - never let one schedule kill the tick.
            failed.append((schedule.id, str(exc)))
            await logger.aerror(
                "ci_scheduled_sync_failed",
                schedule_id=schedule.id,
                error=str(exc),
            )
            continue

        processed.append(schedule.id)

    return {"due": len(due), "processed": processed, "failed": failed}


async def run_due_schedules(
    db: AsyncSession, *, now: datetime | None = None, actor_user_id: str | None = None
) -> dict[str, Any]:
    return await _run_due_schedules_unlocked(db, now=now, actor_user_id=actor_user_id)


async def run_schedule_now(
    db: AsyncSession,
    *,
    org_id: str,
    schedule_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Run one schedule immediately (manual run / retry of a failed sync).

    Unlike :func:`run_due_schedules` this ignores ``next_run_at``: the schedule
    is synced right away and its ``last_run_at`` / ``next_run_at`` are advanced
    as usual. The sync runs with ``trigger="manual"`` so the metrics label
    distinguishes an on-demand run from the cron-driven path.
    """
    correlation_id = gen_id()
    schedule = await CiScheduleRepository(db).get(org_id, schedule_id)
    if schedule is None:
        raise KeyError("schedule not found")
    synced, cases = await _run_one(
        db,
        schedule,
        now=utc_now(),
        actor_user_id=actor_user_id,
        trigger="manual",
        correlation_id=correlation_id,
    )
    return {
        "schedule_id": schedule_id,
        "connection_id": schedule.connection_id,
        "synced": synced,
        "new_cases": cases,
        "correlation_id": correlation_id,
    }


async def _run_one(
    db: AsyncSession,
    schedule: CiSchedule,
    *,
    now: datetime,
    actor_user_id: str | None,
    trigger: str = "scheduled",
    correlation_id: str | None = None,
) -> tuple[int, int]:
    """Sync a single schedule and advance its next run."""
    if not schedule.enabled:
        raise IngestionError("schedule disabled")

    correlation_id = correlation_id or gen_id()
    result = await sync_connection(
        db,
        org_id=schedule.org_id,
        connection_id=schedule.connection_id,
        trigger=trigger,
        max_messages=SCHEDULED_MAX_MESSAGES,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    next_run = compute_next_run_at(schedule.run_time, schedule.timezone, now=now)
    await CiScheduleRepository(db).update(schedule, {"last_run_at": now, "next_run_at": next_run})
    await log_action(
        db,
        org_id=schedule.org_id,
        actor_user_id=actor_user_id,
        action="ci.schedule.ran",
        resource_type="ci_schedule",
        resource_id=schedule.id,
        metadata={
            "connection_id": schedule.connection_id,
            "trigger": trigger,
            "synced": result.get("synced", 0),
            "new_cases": result.get("new_cases", 0),
            "correlation_id": correlation_id,
        },
    )

    synced = result.get("synced", 0)
    cases = result.get("new_cases", 0)
    await logger.ainfo(
        "ci_scheduled_sync_done",
        schedule_id=schedule.id,
        synced=synced,
        new_cases=cases,
        next_run_at=next_run.isoformat(),
        correlation_id=correlation_id,
    )
    return synced, cases


async def process_due_retries(db: AsyncSession, *, max_cases: int = 50) -> dict[str, Any]:
    """Retry due CI cases and move exhausted cases to DEAD_LETTER.

    A case with a report failed during delivery; a case without a report failed
    during research. The distinction is persisted state, not an inference from
    a worker exception.
    """
    from sqlalchemy import func, select

    from app.core.observability.metrics import ci_case_retry_total, ci_dead_letter_gauge
    from app.core.scheduling.backoff import MAX_RETRY_COUNT, compute_backoff_seconds
    from app.customer_intelligence.delivery import DeliveryError, run_delivery
    from app.customer_intelligence.workflow import ResearchError
    from app.models.approval_request import ApprovalRequest
    from app.models.customer_intelligence import ResearchCase
    from app.repositories.customer_intelligence import (
        BriefingReportRepository,
        ResearchCaseRepository,
    )
    from app.services.customer_intelligence_service import CustomerIntelligenceService

    case_repo = ResearchCaseRepository(db)
    report_repo = BriefingReportRepository(db)
    cases = await case_repo.list_due_for_retry(utc_now(), limit=max_cases)
    retried = 0
    dead_lettered = 0
    failed: list[tuple[str, str]] = []

    for case in cases:
        case_id = case.id
        case_org_id = case.org_id
        report = await report_repo.latest_by_case(case.org_id, case.id)
        try:
            if report is None:
                await CustomerIntelligenceService(db).research_case(
                    org_id=case.org_id,
                    case_id=case.id,
                    actor_user_id=None,
                )
            else:
                approval_result = await db.execute(
                    select(ApprovalRequest)
                    .where(
                        ApprovalRequest.org_id == case.org_id,
                        ApprovalRequest.case_id == case.id,
                        ApprovalRequest.status == "approved",
                    )
                    .order_by(ApprovalRequest.decided_at.desc())
                    .limit(1)
                )
                approval = approval_result.scalar_one_or_none()
                if approval is None:
                    raise DeliveryError("approved delivery request not found for retry")
                await case_repo.transition(case, "EXECUTING")
                await run_delivery(
                    db,
                    org_id=case.org_id,
                    case=case,
                    approval=approval,
                    actor_user_id=None,
                )
                await case_repo.transition(case, "COMPLETED")
            retried += 1
            ci_case_retry_total.labels(trigger="auto", outcome="retried").inc()
        except ResearchError as exc:
            failed.append((case_id, type(exc).__name__))
            refreshed = await case_repo.get(case_org_id, case_id)
            if refreshed is None or refreshed.status in {"COMPLETED", "DEAD_LETTER"}:
                continue
            # ResearchError represents a non-transient validation/data problem
            # (for example a missing source email). Retrying it automatically
            # would only create repeated work; an operator can reopen it via
            # the manual retry API after correcting the underlying issue.
            refreshed.error = str(exc)[:4000]
            await case_repo.transition(refreshed, "DEAD_LETTER")
            dead_lettered += 1
            ci_case_retry_total.labels(trigger="auto", outcome="dead_lettered").inc()
        except DeliveryError as exc:
            failed.append((case_id, type(exc).__name__))
            refreshed = await case_repo.get(case_org_id, case_id)
            if refreshed is None or refreshed.status in {"COMPLETED", "DEAD_LETTER"}:
                continue
            # A missing approval or an unsupported/malformed delivery action is
            # a configuration problem, not a transient one - retrying it five
            # times before dead-lettering only delays the operator finding out.
            # EXECUTING cannot transition straight to DEAD_LETTER, so route
            # through RETRYING first (mirrors the state machine's own path).
            refreshed.error = str(exc)[:4000]
            if refreshed.status == "EXECUTING":
                await case_repo.transition(refreshed, "RETRYING")
            if refreshed.status != "DEAD_LETTER":
                await case_repo.transition(refreshed, "DEAD_LETTER")
            dead_lettered += 1
            ci_case_retry_total.labels(trigger="auto", outcome="dead_lettered").inc()
        except Exception as exc:  # noqa: BLE001 - isolate one case from the tick.
            # A failed flush/commit earlier in this iteration (a genuine DB
            # error, not a business-rule DeliveryError/ResearchError) leaves
            # the session unable to run further statements. Roll back before
            # touching anything else so one bad case cannot poison the rest
            # of the batch; use the id captured before the failure since the
            # ORM object's attributes are expired by the rollback.
            await db.rollback()
            failed.append((case_id, type(exc).__name__))
            refreshed = await case_repo.get(case_org_id, case_id)
            if refreshed is None or refreshed.status in {"COMPLETED", "DEAD_LETTER"}:
                continue
            if (
                report is None
                and refreshed.status == "RETRYING"
                and refreshed.next_retry_at is not None
                and refreshed.next_retry_at > utc_now()
            ):
                # CustomerIntelligenceService already recorded the retry for
                # transient research failures; do not increment twice.
                continue
            if refreshed.retry_count >= MAX_RETRY_COUNT:
                refreshed.error = "customer intelligence retry limit exceeded"
                # EXECUTING cannot transition straight to DEAD_LETTER; route
                # through RETRYING first (mirrors the state machine's path).
                if refreshed.status == "EXECUTING":
                    await case_repo.transition(refreshed, "RETRYING")
                await case_repo.transition(refreshed, "DEAD_LETTER")
                dead_lettered += 1
                ci_case_retry_total.labels(trigger="auto", outcome="dead_lettered").inc()
                continue
            await case_repo.schedule_retry(
                refreshed,
                next_retry_at=utc_now()
                + timedelta(seconds=compute_backoff_seconds(refreshed.retry_count)),
                triggered_by=None,
            )

    count_result = await db.execute(
        select(func.count(ResearchCase.id)).where(ResearchCase.status == "DEAD_LETTER")
    )
    ci_dead_letter_gauge.set(int(count_result.scalar_one()))
    return {
        "due": len(cases),
        "retried": retried,
        "dead_lettered": dead_lettered,
        "failed": failed,
    }


async def dispatch_ingested_cases(db: AsyncSession, *, max_cases: int = 100) -> dict[str, Any]:
    """Recover cases whose Redis enqueue failed after successful ingest."""
    from app.repositories.customer_intelligence import ResearchCaseRepository

    cases = await ResearchCaseRepository(db).list_dispatchable(limit=max_cases)
    queued = 0
    failed = 0
    for case in cases:
        try:
            await enqueue_ci_research(case.org_id, case.id)
            queued += 1
        except Exception as exc:  # noqa: BLE001 - next tick retries dispatch.
            failed += 1
            await logger.aerror(
                "ci_research_dispatch_failed",
                org_id=case.org_id,
                case_id=case.id,
                error=str(exc),
            )
    return {"candidates": len(cases), "queued": queued, "failed": failed}
