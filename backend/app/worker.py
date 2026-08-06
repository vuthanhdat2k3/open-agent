from __future__ import annotations

import structlog
from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.core.chat_events import fail_orphaned_chat_runs
from app.core.workflow import resume
from app.core.workflow.jobs import run_chat, run_workflow
from app.core.workflow.queue import enqueue_workflow_run
from app.db.session import SessionLocal
from app.evals.auto_rollback import run_auto_rollback_sweep

logger = structlog.get_logger(__name__)


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


async def _fail_orphaned_chat_runs(ctx: dict) -> None:
    """Chat runs whose stream went silent (worker/API died mid-run) must not
    stay ``running`` forever — the UI would show a spinner that never ends."""
    async with SessionLocal() as db:
        try:
            failed = await fail_orphaned_chat_runs(db)
        except Exception as exc:  # noqa: BLE001
            await logger.aerror("chat_orphan_sweep_failed", error=str(exc))
            return
        if failed:
            await logger.awarning("chat_runs_marked_failed", count=len(failed), run_ids=failed)


class WorkerSettings:
    functions = [run_workflow, run_chat]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = _resume_orphaned_runs
    cron_jobs = [
        cron(_auto_rollback_sweep, minute=set(range(0, 60, 5))),
        cron(_fail_orphaned_chat_runs, minute=set(range(0, 60, 2)), run_at_startup=False),
    ]
