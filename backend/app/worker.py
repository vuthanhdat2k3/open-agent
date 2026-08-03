from __future__ import annotations

import structlog
from arq.connections import RedisSettings

from app.config import get_settings
from app.core.workflow import resume
from app.core.workflow.jobs import run_workflow
from app.core.workflow.queue import enqueue_workflow_run
from app.db.session import SessionLocal

logger = structlog.get_logger(__name__)


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
