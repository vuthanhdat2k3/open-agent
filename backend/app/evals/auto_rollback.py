"""Automatic rollback when a live release's quality regresses.

Off by default and per-agent: automatically swapping the production
configuration out from under a running agent is a strong action, so an
operator has to opt in rather than discover it after the fact. When
enabled, it reuses the exact rollback mechanism M10 already exposes to
humans — this is not a second code path with its own risk profile.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.db.base import utc_now
from app.evals.quality_gate import quality_gate_passes
from app.models.agent import Agent
from app.models.agent_release import AgentRelease
from app.models.audit_log import AuditLog
from app.models.evaluation import EvaluationRun, EvaluationSuite


async def _last_rollback_at(db: AsyncSession, org_id: str, agent_id: str):
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.org_id == org_id,
            AuditLog.action == "agent.release.auto_rolled_back",
            AuditLog.resource_id == agent_id,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row.created_at if row else None


async def check_agent_for_rollback(db: AsyncSession, agent: Agent) -> AgentRelease | None:
    """Roll an agent's active release back if it just regressed.

    Returns the release rolled back to, or ``None`` if nothing happened
    (feature off, no recent run, gate passing, still in cooldown, or no
    earlier release to fall back to).
    """
    if not agent.auto_rollback_enabled or not agent.active_release_id:
        return None

    cooldown = timedelta(minutes=agent.auto_rollback_cooldown_minutes)
    last_rollback = await _last_rollback_at(db, agent.org_id, agent.id)
    if last_rollback is not None and utc_now() - last_rollback < cooldown:
        # A run flapping between two releases is worse than staying on a
        # degraded one for a few more minutes.
        return None

    run_result = await db.execute(
        select(EvaluationRun)
        .where(
            EvaluationRun.org_id == agent.org_id,
            EvaluationRun.agent_release_id == agent.active_release_id,
            EvaluationRun.status == "completed",
        )
        .order_by(EvaluationRun.created_at.desc())
        .limit(1)
    )
    latest_run = run_result.scalar_one_or_none()
    if latest_run is None:
        return None

    min_pass_rate = agent.auto_rollback_min_pass_rate
    if min_pass_rate is None:
        suite_result = await db.execute(
            select(EvaluationSuite).where(
                EvaluationSuite.id == latest_run.suite_id, EvaluationSuite.org_id == agent.org_id
            )
        )
        suite = suite_result.scalar_one_or_none()
        min_pass_rate = getattr(suite, "min_pass_rate", 0.8) if suite else 0.8

    if quality_gate_passes(pass_rate=latest_run.pass_rate, min_pass_rate=min_pass_rate):
        return None

    releases_result = await db.execute(
        select(AgentRelease)
        .where(
            AgentRelease.org_id == agent.org_id,
            AgentRelease.agent_id == agent.id,
            AgentRelease.status.in_(("published", "archived")),
            AgentRelease.id != agent.active_release_id,
        )
        .order_by(AgentRelease.version.desc())
        .limit(1)
    )
    fallback = releases_result.scalar_one_or_none()
    if fallback is None:
        # Nothing to fall back to; failing loudly here would just be noise
        # on every sweep until a human intervenes.
        return None

    # Imported locally: agent_service imports quality_gate at module load,
    # so a top-level import here would create a cycle.
    from app.services.agent_service import AgentService

    rolled_back_from = agent.active_release_id
    release = await AgentService(db).rollback_release(agent.org_id, agent.id, fallback.version)

    await log_action(
        db,
        org_id=agent.org_id,
        action="agent.release.auto_rolled_back",
        resource_type="agent",
        resource_id=agent.id,
        metadata={
            "rolled_back_from_release_id": rolled_back_from,
            "rolled_back_to_version": fallback.version,
            "evaluation_run_id": latest_run.id,
            "pass_rate": latest_run.pass_rate,
            "min_pass_rate": min_pass_rate,
        },
    )
    return release


async def run_auto_rollback_sweep(db: AsyncSession) -> list[str]:
    """Check every agent with auto-rollback enabled. Returns agent ids rolled back."""
    result = await db.execute(select(Agent).where(Agent.auto_rollback_enabled.is_(True)))
    rolled_back: list[str] = []
    for agent in result.scalars().all():
        if await check_agent_for_rollback(db, agent) is not None:
            rolled_back.append(agent.id)
    return rolled_back
