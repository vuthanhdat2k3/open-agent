"""M15 — publish quality gate and auto-rollback.

Two invariants matter here:

1. Publishing over a red gate requires an explicit, owner-only, audited
   override (covered end to end in test_agent_releases.py).
2. Auto-rollback is opt-in per agent, respects a cooldown so it cannot
   flap between releases, and reuses the exact rollback path a human
   would use rather than a second, less-tested code path.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base, gen_id, utc_now
from app.evals.auto_rollback import check_agent_for_rollback, run_auto_rollback_sweep
from app.evals.quality_gate import quality_gate_passes
from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.evaluation import EvaluationRun, EvaluationSuite
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.services.agent_service import AgentService


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed_published_agent(
    db: AsyncSession, *, auto_rollback_enabled: bool = False
) -> Agent:
    org = Organization(name="Rollback Org", slug=f"rollback-org-{gen_id()}")
    db.add(org)
    await db.commit()
    await db.refresh(org)

    provider = Provider(
        org_id=org.id, name="OpenAI", key="openai", base_url="http://x", api_key="k"
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    model = Model(
        org_id=org.id, provider_id=provider.id, name="gpt-4o-mini", display_name="GPT-4o mini"
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    svc = AgentService(db)
    agent = await svc.create(
        org.id,
        {
            "name": "rollback-target",
            "model_id": model.id,
            "system_prompt": "v1",
            "auto_rollback_enabled": auto_rollback_enabled,
            "auto_rollback_cooldown_minutes": 30,
        },
    )
    # Publish a second release so there is something to fall back to.
    draft = await svc.create_release(org.id, agent.id, {"system_prompt": "v2"})
    await svc.publish_release(org.id, agent.id, draft.version)
    return await svc.repo.get(org.id, agent.id)


async def _failing_run_for_active_release(db: AsyncSession, agent: Agent) -> EvaluationRun:
    # Unique name: this helper may run more than once per org in one test
    # (repeated regressions, tenant-isolation checks) and suite names are
    # unique per org.
    suite = EvaluationSuite(
        org_id=agent.org_id, agent_id=agent.id, name=f"Rollback Suite {gen_id()}"
    )
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    run = EvaluationRun(
        org_id=agent.org_id,
        suite_id=suite.id,
        agent_release_id=agent.active_release_id,
        dataset_version=suite.dataset_version,
        execution_mode="recorded",
        status="completed",
        pass_rate=0.2,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


# --------------------------------------------------------------------------- #
# quality_gate_passes (pure function; pinned here alongside the rollback
# behaviour that depends on it)
# --------------------------------------------------------------------------- #
def test_quality_gate_fails_below_threshold() -> None:
    assert quality_gate_passes(pass_rate=0.5, min_pass_rate=0.8) is False
    assert quality_gate_passes(pass_rate=0.9, min_pass_rate=0.8) is True


# --------------------------------------------------------------------------- #
# Auto-rollback
# --------------------------------------------------------------------------- #
async def test_disabled_by_default_does_nothing(session_factory) -> None:
    async with session_factory() as db:
        agent = await _seed_published_agent(db, auto_rollback_enabled=False)
        await _failing_run_for_active_release(db, agent)

        result = await check_agent_for_rollback(db, agent)

    assert result is None, "auto-rollback must be opt-in"


async def test_regressed_release_triggers_rollback(session_factory) -> None:
    async with session_factory() as db:
        agent = await _seed_published_agent(db, auto_rollback_enabled=True)
        active_before = agent.active_release_id
        await _failing_run_for_active_release(db, agent)

        rolled_back_to = await check_agent_for_rollback(db, agent)

        result = await db.execute(select(Agent).where(Agent.id == agent.id))
        refreshed = result.scalar_one()

    assert rolled_back_to is not None
    assert refreshed.active_release_id != active_before, "the release must actually change"


async def test_rollback_is_audited(session_factory) -> None:
    async with session_factory() as db:
        agent = await _seed_published_agent(db, auto_rollback_enabled=True)
        await _failing_run_for_active_release(db, agent)

        await check_agent_for_rollback(db, agent)

        result = await db.execute(
            select(AuditLog).where(
                AuditLog.org_id == agent.org_id,
                AuditLog.action == "agent.release.auto_rolled_back",
            )
        )
        rows = list(result.scalars().all())

    assert len(rows) == 1
    assert rows[0].metadata_["pass_rate"] == 0.2


async def test_cooldown_prevents_flapping(session_factory) -> None:
    """A second regression inside the cooldown window must not roll back again."""
    async with session_factory() as db:
        agent = await _seed_published_agent(db, auto_rollback_enabled=True)
        await _failing_run_for_active_release(db, agent)
        first = await check_agent_for_rollback(db, agent)
        assert first is not None

        result = await db.execute(select(Agent).where(Agent.id == agent.id))
        refreshed = result.scalar_one()
        await _failing_run_for_active_release(db, refreshed)

        second = await check_agent_for_rollback(db, refreshed)

    assert second is None, "cooldown must block a second rollback right after the first"


async def test_cooldown_expires(session_factory) -> None:
    async with session_factory() as db:
        agent = await _seed_published_agent(db, auto_rollback_enabled=True)
        await _failing_run_for_active_release(db, agent)
        await check_agent_for_rollback(db, agent)

        # Simulate the cooldown having elapsed.
        result = await db.execute(
            select(AuditLog).where(AuditLog.action == "agent.release.auto_rolled_back")
        )
        row = result.scalars().one()
        row.created_at = utc_now() - timedelta(minutes=agent.auto_rollback_cooldown_minutes + 1)
        await db.commit()

        result = await db.execute(select(Agent).where(Agent.id == agent.id))
        refreshed = result.scalar_one()
        await _failing_run_for_active_release(db, refreshed)

        second = await check_agent_for_rollback(db, refreshed)

    assert second is not None, "rollback must be available again once cooldown elapses"


async def test_passing_gate_does_not_roll_back(session_factory) -> None:
    async with session_factory() as db:
        agent = await _seed_published_agent(db, auto_rollback_enabled=True)
        suite = EvaluationSuite(org_id=agent.org_id, agent_id=agent.id, name="Passing Suite")
        db.add(suite)
        await db.commit()
        await db.refresh(suite)
        db.add(
            EvaluationRun(
                org_id=agent.org_id,
                suite_id=suite.id,
                agent_release_id=agent.active_release_id,
                dataset_version=suite.dataset_version,
                execution_mode="recorded",
                status="completed",
                pass_rate=0.95,
            )
        )
        await db.commit()

        result = await check_agent_for_rollback(db, agent)

    assert result is None


async def test_no_fallback_release_does_nothing(session_factory) -> None:
    """An agent with only one release has nowhere to roll back to."""
    async with session_factory() as db:
        org = Organization(name="Solo Org", slug="solo-org")
        db.add(org)
        await db.commit()
        await db.refresh(org)
        provider = Provider(
            org_id=org.id, name="OpenAI", key="openai", base_url="http://x", api_key="k"
        )
        db.add(provider)
        await db.commit()
        await db.refresh(provider)
        model = Model(
            org_id=org.id, provider_id=provider.id, name="gpt-4o-mini", display_name="m"
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)

        svc = AgentService(db)
        agent = await svc.create(
            org.id,
            {
                "name": "solo",
                "model_id": model.id,
                "system_prompt": "only",
                "auto_rollback_enabled": True,
            },
        )
        await _failing_run_for_active_release(db, agent)

        result = await check_agent_for_rollback(db, agent)

    assert result is None


async def test_sweep_only_checks_opted_in_agents(session_factory) -> None:
    async with session_factory() as db:
        enabled = await _seed_published_agent(db, auto_rollback_enabled=True)
        disabled = await _seed_published_agent(db, auto_rollback_enabled=False)
        await _failing_run_for_active_release(db, enabled)
        await _failing_run_for_active_release(db, disabled)

        rolled_back = await run_auto_rollback_sweep(db)

    assert enabled.id in rolled_back
    assert disabled.id not in rolled_back
