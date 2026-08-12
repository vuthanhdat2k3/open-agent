"""ARQ job that runs Customer Intelligence research after ingest.

``sync_connection`` (ingest.py) only creates a case in ``INGESTED`` status;
nothing drove it to ``REPORT_READY`` automatically before this job existed,
so a synced case sat unresearched until someone called the research API by
hand. This closes that gap: the ingest path enqueues one job per new case, and
the worker picks it up off the Redis queue instead of running research inline
during the sync tick (research does web/news/company/calendar I/O and must
not block the scheduler cron or a manual sync request).
"""

from __future__ import annotations

from typing import Any

import structlog
from arq import Retry

from app.db.session import SessionLocal
from app.repositories.customer_intelligence import ResearchCaseRepository

logger = structlog.get_logger(__name__)

# Research calls out to web search, news search, company lookup and calendar
# providers - all soft-fail individually, but a hard failure (provider outage,
# transient DB error) should not be treated as permanent on the first try.
_MAX_RESEARCH_TRIES = 3
_RETRY_BASE_SECONDS = 30


async def run_ci_research(ctx: dict[str, Any], org_id: str, case_id: str) -> None:
    """Research one ingested Customer Intelligence case.

    Re-reads the case in the worker process rather than trusting the enqueue
    payload: by the time this job runs the case may already have moved past
    ``INGESTED``/``RETRYING`` (manual research via the API, or a duplicate
    enqueue), in which case there is nothing to do.
    """
    from app.customer_intelligence.workflow import ResearchError, run_research

    async with SessionLocal() as db:
        case = await ResearchCaseRepository(db).get(org_id, case_id)
        if case is None or case.status not in {"INGESTED", "RETRYING"}:
            return
        try:
            await run_research(db, org_id=org_id, case_id=case_id, actor_user_id=None)
        except ResearchError as exc:
            # Not researchable (bad state, missing email) - retrying will not
            # help, so log it and stop instead of burning retry attempts.
            await logger.aerror(
                "ci_auto_research_rejected", org_id=org_id, case_id=case_id, error=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 - transient provider/DB failure, worth a retry.
            job_try = int(ctx.get("job_try", 1))
            await logger.awarning(
                "ci_auto_research_failed",
                org_id=org_id,
                case_id=case_id,
                job_try=job_try,
                error=str(exc),
            )
            if job_try < _MAX_RESEARCH_TRIES:
                raise Retry(defer=_RETRY_BASE_SECONDS * (2 ** (job_try - 1))) from exc
            await logger.aerror(
                "ci_auto_research_exhausted", org_id=org_id, case_id=case_id
            )
