from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def enqueue_workflow_run(workflow_run_id: str) -> str:
    pool = await create_pool(_redis_settings())
    try:
        job = await pool.enqueue_job("run_workflow", workflow_run_id)
        return job.job_id if job else ""
    finally:
        await pool.close()

