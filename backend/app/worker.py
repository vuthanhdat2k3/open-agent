from __future__ import annotations

import os
import socket

import structlog
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import get_settings
from app.core.chat_events import fail_orphaned_chat_runs
from app.core.observability.llm_trace import NoopSink, set_default_sink
from app.core.outbox import publish_pending_outbox
from app.core.providers.jobs import run_provider_discovery
from app.core.workflow import resume
from app.core.workflow.jobs import run_chat, run_workflow
from app.core.workflow.queue import enqueue_workflow_run
from app.customer_intelligence.jobs import run_ci_research
from app.db.session import SessionLocal
from app.evals.auto_rollback import run_auto_rollback_sweep

logger = structlog.get_logger(__name__)
_langfuse_sink = None
_worker_id: str | None = None


async def _auto_rollback_sweep(ctx: dict) -> None:
    async with SessionLocal() as db:
        try:
            rolled_back = await run_auto_rollback_sweep(db)
        except Exception as exc:  # noqa: BLE001
            await logger.aerror("auto_rollback_sweep_failed", error=str(exc))
            return
        if rolled_back:
            await logger.awarning("agents_auto_rolled_back", agent_ids=rolled_back)


async def _resume_orphaned_runs(ctx: dict) -> None:
    async with SessionLocal() as db:
        try:
            run_ids = await resume.sweep_orphans(db)
        except Exception as exc:  # noqa: BLE001
            await logger.aerror("orphan_sweep_failed", error=str(exc))
            return
        for run_id in run_ids:
            try:
                await enqueue_workflow_run(run_id)
            except Exception as exc:  # noqa: BLE001
                await logger.aerror("orphan_enqueue_failed", run_id=run_id, error=str(exc))
        if run_ids:
            await logger.ainfo("orphan_runs_resumed", count=len(run_ids), run_ids=run_ids)


async def _startup(ctx: dict) -> None:
    global _langfuse_sink, _worker_id
    _worker_id = f"{socket.gethostname()}-{os.getpid()}"
    await _resume_orphaned_runs(ctx)
    settings = get_settings()
    if settings.observability_enabled and settings.langfuse_enabled:
        from app.core.observability.langfuse_sink import build_langfuse_sink

        _langfuse_sink = build_langfuse_sink(settings)
        if _langfuse_sink:
            set_default_sink(_langfuse_sink)


def _worker_identity() -> str:
    return _worker_id or f"{socket.gethostname()}-{os.getpid()}"


async def _shutdown(ctx: dict) -> None:
    global _langfuse_sink
    if _langfuse_sink:
        _langfuse_sink.flush(get_settings().langfuse_flush_timeout_seconds)
    _langfuse_sink = None
    set_default_sink(NoopSink())


async def _fail_orphaned_chat_runs(ctx: dict) -> None:
    """Chat runs whose stream went silent (worker/API died mid-run) must not
    stay ``running`` forever â€” the UI would show a spinner that never ends."""
    async with SessionLocal() as db:
        try:
            failed = await fail_orphaned_chat_runs(db)
        except Exception as exc:  # noqa: BLE001
            await logger.aerror("chat_orphan_sweep_failed", error=str(exc))
            return
        if failed:
            await logger.awarning("chat_runs_marked_failed", count=len(failed), run_ids=failed)


async def _ci_scheduler_tick(ctx: dict) -> None:
    """Run due Customer-Intelligence sync schedules with a DB lease."""
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import run_due_schedules

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_SCHEDULER_TICK,
            interval_seconds=300,
            lease_seconds=240,
            worker_id=_worker_identity(),
            run=lambda: run_due_schedules(db),
        )


async def _workflow_scheduler_tick(ctx: dict) -> None:
    """Materialize due personal workflow occurrences through the durable outbox."""
    from app.core.scheduling.tick import run_leased_tick
    from app.workflows.scheduler import run_due_workflows

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key="workflow_scheduler_tick",
            interval_seconds=60,
            lease_seconds=50,
            worker_id=_worker_identity(),
            run=lambda: run_due_workflows(db),
        )


async def _ci_retry_due_cases_tick(ctx: dict) -> None:
    """Retry due CI cases and record failures without stopping ARQ."""
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import process_due_retries

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_RETRY_DUE_CASES,
            interval_seconds=60,
            lease_seconds=50,
            worker_id=_worker_identity(),
            run=lambda: process_due_retries(db),
        )


async def _ci_dispatch_ingested_tick(ctx: dict) -> None:
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import dispatch_ingested_cases

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_DISPATCH_INGESTED,
            interval_seconds=60,
            lease_seconds=50,
            worker_id=_worker_identity(),
            run=lambda: dispatch_ingested_cases(db),
        )


async def _outbox_dispatch_tick(ctx: dict) -> None:
    """Publish durable DB events to ARQ; Postgres remains the retry source."""
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_OUTBOX_DISPATCH,
            interval_seconds=1,
            lease_seconds=30,
            worker_id=_worker_identity(),
            run=lambda: publish_pending_outbox(db, owner=_worker_identity()),
        )


async def _gmail_reconciliation_tick(ctx: dict) -> None:
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import enqueue_gmail_maintenance_events

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_GMAIL_RECONCILIATION,
            interval_seconds=300,
            lease_seconds=240,
            worker_id=_worker_identity(),
            run=lambda: enqueue_gmail_maintenance_events(db),
        )


async def _gmail_watch_renewal_tick(ctx: dict) -> None:
    from app.core.scheduling.job_keys import JobKey
    from app.core.scheduling.tick import run_leased_tick
    from app.customer_intelligence.scheduler import enqueue_gmail_maintenance_events

    async with SessionLocal() as db:
        await run_leased_tick(
            db,
            job_key=JobKey.CI_GMAIL_WATCH_RENEWAL,
            interval_seconds=43200,
            lease_seconds=3600,
            worker_id=_worker_identity(),
            run=lambda: enqueue_gmail_maintenance_events(db),
        )


async def process_outbox_event(ctx: dict, event_id: str) -> None:
    """Consume known events exactly once; unknown events fail visibly."""
    from app.models.outbox import OutboxEvent, ProcessedEvent
    from app.repositories.outbox import OutboxRepository

    async with SessionLocal() as db:
        event = await db.get(OutboxEvent, event_id)
        if event is None:
            return
        repo = OutboxRepository(db)
        consumer_name = (
            "classification-worker"
            if event.event_type == "email.classification.requested"
            else "worker"
        )
        already_processed = await db.scalar(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == event.id,
                ProcessedEvent.consumer_name == consumer_name,
            )
        )
        if already_processed:
            return
        if event.event_type == "ci.research.requested":
            await run_ci_research(ctx, event.org_id, event.aggregate_id)
            await repo.mark_processed(event_id=event.id, consumer_name="worker")
            await db.commit()
            return
        if event.event_type == "ci.delivery.requested":
            from app.customer_intelligence.delivery import DeliveryError, run_delivery
            from app.db.base import utc_now
            from app.models.approval_request import ApprovalRequest
            from app.models.customer_intelligence import ResearchCase

            approval = await db.get(ApprovalRequest, event.payload.get("approval_id"))
            case = await db.get(ResearchCase, event.payload.get("case_id"))
            if (
                approval is None
                or case is None
                or approval.org_id != event.org_id
                or case.org_id != event.org_id
            ):
                raise RuntimeError("delivery event references invalid ownership")
            if approval.status != "approved" or case.status == "COMPLETED":
                await repo.mark_processed(event_id=event.id, consumer_name="worker")
                await db.commit()
                return
            if case.status != "APPROVED":
                raise RuntimeError(f"delivery case is not approved (status={case.status})")
            case.status = "EXECUTING"
            await db.commit()
            try:
                attempt = await run_delivery(
                    db,
                    org_id=event.org_id,
                    case=case,
                    approval=approval,
                    actor_user_id=approval.decided_by,
                )
            except DeliveryError as exc:
                case = await db.get(ResearchCase, case.id)
                if case is not None and case.status == "EXECUTING":
                    case.status = "RETRYING"
                    case.error = str(exc)[:4000]
                    case.next_retry_at = utc_now()
                    case.retry_count += 1
                await repo.mark_processed(event_id=event.id, consumer_name="worker")
                await db.commit()
                return
            case = await db.get(ResearchCase, case.id)
            if case is not None:
                case.status = "COMPLETED"
            await repo.mark_processed(event_id=event.id, consumer_name="worker")
            await db.commit()
            return
        if event.event_type == "email.classification.requested":
            from app.customer_intelligence.classification_service import (
                classify_and_route_email,
            )

            await classify_and_route_email(
                db,
                org_id=event.org_id,
                email_id=event.aggregate_id,
                expected_content_hash=event.payload.get("content_hash"),
                correlation_id=event.correlation_id,
                trigger=event.payload.get("trigger", "webhook"),
            )
            await repo.mark_processed(event_id=event.id, consumer_name=consumer_name)
            await db.commit()
            return
        if event.event_type == "gmail.history_sync.requested":
            from app.customer_intelligence.ingest import sync_connection

            await sync_connection(
                db,
                org_id=event.org_id,
                connection_id=event.aggregate_id,
                trigger="webhook",
                correlation_id=event.correlation_id,
                history_id=event.payload.get("history_id"),
            )
            await repo.mark_processed(event_id=event.id, consumer_name="worker")
            await db.commit()
            return
        if event.event_type == "gmail.reconciliation.requested":
            from app.customer_intelligence.ingest import sync_connection

            await sync_connection(
                db,
                org_id=event.org_id,
                connection_id=event.aggregate_id,
                trigger="reconciliation",
                correlation_id=event.correlation_id,
            )
            await repo.mark_processed(event_id=event.id, consumer_name="worker")
            await db.commit()
            return
        if event.event_type == "gmail.watch.renew.requested":
            from app.customer_intelligence.oauth import load_fresh_credentials
            from app.customer_intelligence.providers.email import (
                bind_email_provider,
                get_email_provider,
            )
            from app.models.customer_intelligence import EmailConnection

            connection = await db.get(EmailConnection, event.aggregate_id)
            if connection is None or connection.org_id != event.org_id:
                return
            credentials = await load_fresh_credentials(db, connection)
            provider = bind_email_provider(get_email_provider("gmail"), credentials)
            result = await provider.watch(topic_name=get_settings().gmail_pubsub_topic)
            # The watch response is not a processing checkpoint. Advancing
            # gmail_history_id here could skip deltas that are still queued.
            # The ingest worker advances it only after history/bootstrap data
            # has been durably processed.
            expiration = result.get("expiration") or result.get("expiration_at")
            if expiration:
                from datetime import datetime

                connection.watch_expiration_at = datetime.fromisoformat(str(expiration).replace("Z", "+00:00")).replace(tzinfo=None)
            connection.watch_resource_name = result.get("resource_name") or result.get("resourceName")
            await repo.mark_processed(event_id=event.id, consumer_name="worker")
            await db.commit()
            return
        if event.event_type == "workflow.run.requested":
            from app.db.base import utc_now
            from app.models.workflow_occurrence import WorkflowOccurrence

            run_id = event.payload.get("run_id")
            if not run_id:
                raise RuntimeError("workflow.run.requested missing run_id")
            await enqueue_workflow_run(run_id)
            occurrence = await db.get(WorkflowOccurrence, event.aggregate_id)
            if occurrence is not None:
                occurrence.status = "dispatched"
                occurrence.dispatched_at = utc_now()
            await repo.mark_processed(event_id=event.id, consumer_name="worker")
            await db.commit()
            return
        raise RuntimeError(f"unsupported outbox event type: {event.event_type}")


class WorkerSettings:
    functions = [run_workflow, run_chat, run_provider_discovery, run_ci_research, process_outbox_event]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = _startup
    on_shutdown = _shutdown
    cron_jobs = [
        cron(_auto_rollback_sweep, minute=set(range(0, 60, 5))),
        cron(_fail_orphaned_chat_runs, minute=set(range(0, 60, 2)), run_at_startup=False),
        cron(_ci_scheduler_tick, minute=set(range(0, 60, 5)), run_at_startup=False),
        cron(_workflow_scheduler_tick, minute=set(range(0, 60, 1)), run_at_startup=False),
        cron(_ci_retry_due_cases_tick, minute=set(range(0, 60, 1)), run_at_startup=False),
        cron(_ci_dispatch_ingested_tick, minute=set(range(0, 60, 1)), run_at_startup=False),
        cron(_outbox_dispatch_tick, second=set(range(0, 60, 1)), run_at_startup=False),
        cron(_gmail_reconciliation_tick, minute=set(range(0, 60, 5)), run_at_startup=False),
        cron(_gmail_watch_renewal_tick, hour=set(range(0, 24, 12)), minute=0, run_at_startup=False),
    ]


class ClassificationWorkerSettings:
    functions = [process_outbox_event]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = "arq:ci:classify"
    max_jobs = 4
    job_timeout = 60
