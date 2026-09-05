"""Periodic invocation of the Ops & Reliability agent, one sweep per org.

Each org that has materialized the "ops-reliability" system agent gets its
own fresh session per sweep (per the approved plan: "mỗi lần sweep = 1
session mới") so findings/history stay cleanly scoped per run instead of
accumulating in one giant thread.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop import run_agent_loop
from app.core.execution_policy import ExecutionPolicy
from app.db.base import utc_now
from app.models.agent import Agent
from app.models.session import Session

SWEEP_INSTRUCTION = (
    "Run your scheduled scan sweep now. Look for anomalies in roughly the "
    "last 15 minutes: query_langfuse_traces (level=ERROR, then WARNING if "
    "nothing found) and query_system_health. For every distinct anomaly, "
    "record a finding via record_ops_finding. Only attempt a fix when you "
    "have a clear, evidence-backed root cause."
)


async def run_ops_agent_sweep(db: AsyncSession) -> int:
    """Invoke the ops-reliability agent for every org that has one.

    Returns the number of orgs swept. Failures for one org must not stop the
    sweep for the rest - each org's run is isolated in its own try/except so
    a single misbehaving org (or agent misconfiguration) never blocks the
    whole tick, matching run_leased_tick's own single-failure-doesn't-crash
    contract at the outer level.
    """
    result = await db.execute(select(Agent).where(Agent.template_key == "ops-reliability"))
    agents = list(result.scalars().all())
    swept = 0
    for agent in agents:
        try:
            session = Session(
                org_id=agent.org_id,
                created_by_user_id=None,
                agent_id=agent.id,
                agent_release_id=agent.active_release_id,
                title=f"Ops sweep {utc_now().isoformat(timespec='minutes')}",
                execution_policy=ExecutionPolicy.manual.value,
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)

            await run_agent_loop(
                agent,
                SWEEP_INSTRUCTION,
                db,
                session_id=session.id,
                execution_policy=ExecutionPolicy.manual,
            )
            swept += 1
        except Exception:  # noqa: BLE001
            await db.rollback()
            continue
    return swept
