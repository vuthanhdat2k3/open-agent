from __future__ import annotations

import structlog
from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.core.workflow import resume
from app.core.workflow.jobs import run_workflow
from app.core.workflow.queue import enqueue_workflow_run
from app.db.session import SessionLocal
from app.evals.auto_rollback import run_auto_rollback_sweep

logger = structlog.get_logger(__name__)


async def _auto_rollback_sweep(ctx: dict) -> None:
    """Check every auto-rollback-enabled agent for a regressed release.

    Runs regardless of whether any agent has the feature on — the query is
    a single indexed lookup when nobody has opted in, and this is the only
    thing driving the trace -> eval -> gate -> rollback loop when nobody is
    actively publishing right now.
    """
    async with SessionLocal() as db:
        try:
            rolled_back = await run_auto_rollback_sweep(db)
        except Exception as exc:  # noqa: BLE001 - a cron tick must not crash the worker
            await logger.aerror("auto_rollback_sweep_failed", error=str(exc))
            return
        if rolled_back:
            await logger.awarning("agents_auto_rolled_back", agent_ids=rolled_back)


async def _resume_orphaned_runs(ctx: dict) -> None:
    """Re-queue runs whose worker died mid-flight.

    Without this, a killed worker leaves runs stuck in ``running`` forever
    with nothing driving them. The lease inside ``sweep_orphans`` guarantees
    only one worker claims each run, so this is safe to do on every boot.

    A failure here must not stop the worker from starting: losing orphan
    recovery is bad, refusing to process any new work is worse.
    """
    async with SessionLocal() as db:
        try:
            run_ids = await resume.sweep_orphans(db)
        except Exception as exc:  # noqa: BLE001 - startup must stay resilient
            await logger.aerror("orphan_sweep_failed", error=str(exc))
            return

        for run_id in run_ids:
            await enqueue_workflow_run(run_id)
        if run_ids:
            await logger.ainfo("orphan_runs_resumed", count=len(run_ids), run_ids=run_ids)


class WorkerSettings:
    functions = [run_workflow]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = _resume_orphaned_runs
    cron_jobs = [cron(_auto_rollback_sweep, minute=set(range(0, 60, 5)))]
