from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def _enqueue(function: str, *args: Any) -> str:
    pool = await create_pool(_redis_settings())
    try:
        job = await pool.enqueue_job(function, *args)
        return job.job_id if job else ""
    finally:
        await pool.close()


async def enqueue_workflow_run(workflow_run_id: str) -> str:
    return await _enqueue("run_workflow", workflow_run_id)


async def enqueue_chat_run(payload: dict[str, Any]) -> str:
    return await _enqueue("run_chat", payload)


async def enqueue_provider_discovery(provider_id: str, discovery_generation: int) -> str:
    return await _enqueue("run_provider_discovery", provider_id, discovery_generation)


async def enqueue_ci_research(org_id: str, case_id: str) -> str:
    return await _enqueue("run_ci_research", org_id, case_id)
