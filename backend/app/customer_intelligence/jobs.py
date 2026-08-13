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

from app.db.session import SessionLocal

logger = structlog.get_logger(__name__)

async def run_ci_research(ctx: dict[str, Any], org_id: str, case_id: str) -> None:
    """Research one ingested Customer Intelligence case.

    Re-reads the case in the worker process rather than trusting the enqueue
    payload: by the time this job runs the case may already have moved past
    ``INGESTED``/``RETRYING`` (manual research via the API, or a duplicate
    enqueue), in which case there is nothing to do.
    """
    from app.customer_intelligence.workflow import ResearchError
    from app.services.customer_intelligence_service import CustomerIntelligenceService

    async with SessionLocal() as db:
        try:
            await CustomerIntelligenceService(db).research_case(
                org_id=org_id, case_id=case_id, actor_user_id=None
            )
        except ResearchError as exc:
            # Not researchable (bad state, missing email) - retrying will not
            # help, so log it and stop instead of burning retry attempts.
            await logger.aerror(
                "ci_auto_research_rejected", org_id=org_id, case_id=case_id, error=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 - durable retry state is recorded.
            await logger.awarning(
                "ci_auto_research_failed",
                org_id=org_id,
                case_id=case_id,
                job_try=int(ctx.get("job_try", 1)),
                error=str(exc),
                exc_info=True,
            )
