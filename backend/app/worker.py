from __future__ import annotations

from arq.connections import RedisSettings

from app.config import get_settings
from app.core.workflow.jobs import run_workflow


class WorkerSettings:
    functions = [run_workflow]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

