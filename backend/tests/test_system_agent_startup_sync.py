from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.agent_loop import _build_orchestrator_delegate_tools
from app.core.agents.sync import sync_system_agents_all_orgs, sync_system_agents_for_org
from app.core.agents.templates import SYSTEM_AGENT_BLUEPRINTS
from app.db.base import Base, gen_id
from app.models.agent import Agent
from app.models.model import Model
from app.models.org_agent_settings import OrgAgentSettings
from app.models.organization import Organization
from app.models.provider import Provider


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


async def _seed_org_with_model(db: AsyncSession) -> tuple[str, str]:
    org = Organization(id=gen_id(), name="Sync Org", slug="sync-org")
    provider = Provider(
        id=gen_id(),
        org_id=org.id,
        key="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
    )
    model = Model(
        id=gen_id(),
        org_id=org.id,
        provider_id=provider.id,
        name="gpt-4o-mini",
        display_name="GPT-4o Mini",
        tier="fast",
        active=True,
    )
    db.add(org)
    db.add(provider)
    db.add(model)
    await db.commit()
    return org.id, model.id


@pytest.mark.asyncio
async def test_startup_sync_materializes_all_blueprints(async_session_factory) -> None:
    async with async_session_factory() as db:
        org_id, _ = await _seed_org_with_model(db)
        results = await sync_system_agents_all_orgs(db)

    assert len(results) == 1
    assert results[0].org_id == org_id
    assert results[0].created == len(SYSTEM_AGENT_BLUEPRINTS)

    async with async_session_factory() as db:
        agents = (
            await db.scalars(select(Agent).where(Agent.org_id == org_id))
        ).all()
        assert len(agents) == len(SYSTEM_AGENT_BLUEPRINTS)
        assert {agent.template_key for agent in agents} == set(SYSTEM_AGENT_BLUEPRINTS.keys())
        assert sum(1 for agent in agents if agent.kind == "worker") == 11
        assert sum(1 for agent in agents if agent.kind == "orchestrator") == 1


@pytest.mark.asyncio
async def test_startup_sync_is_idempotent(async_session_factory) -> None:
    async with async_session_factory() as db:
        org_id, _ = await _seed_org_with_model(db)
        first = await sync_system_agents_all_orgs(db)
        second = await sync_system_agents_all_orgs(db)

    assert first[0].created == len(SYSTEM_AGENT_BLUEPRINTS)
    assert second[0].created == 0
    assert second[0].updated == 0

    async with async_session_factory() as db:
        agents = (await db.scalars(select(Agent).where(Agent.org_id == org_id))).all()
        assert len(agents) == len(SYSTEM_AGENT_BLUEPRINTS)


@pytest.mark.asyncio
async def test_startup_sync_backfills_missing_workers_for_existing_orchestrator(
    async_session_factory,
) -> None:
    async with async_session_factory() as db:
        org_id, model_id = await _seed_org_with_model(db)
        orchestrator = Agent(
            id="sys-agent-general",
            org_id=org_id,
            name="General Assistant",
            description="Primary orchestrator",
            system_prompt="orchestrator",
            model_id=model_id,
            tools=["call_agent", "workflow_list", "get_current_time", "save_memory", "call_memory"],
            allowed_risk_tiers=["safe", "read", "network", "execute"],
            kind="orchestrator",
            template_key="general",
            is_customized=False,
        )
        db.add(orchestrator)
        await db.commit()

        result = await sync_system_agents_for_org(db, org_id)
        await db.commit()

        roster, specs, _, _ = await _build_orchestrator_delegate_tools(
            db, org_id, orchestrator.id
        )

    assert result.created == len(SYSTEM_AGENT_BLUEPRINTS) - 1
    assert len(specs) == 11
    assert "Deep Web Researcher" in roster
    assert any(spec.name.startswith("delegate_to_") for spec in specs)


@pytest.mark.asyncio
async def test_startup_sync_skips_disabled_blueprints(async_session_factory) -> None:
    async with async_session_factory() as db:
        org_id, _ = await _seed_org_with_model(db)
        db.add(
            OrgAgentSettings(
                org_id=org_id,
                template_key="deep-researcher",
                is_enabled=False,
                is_pinned=False,
            )
        )
        await db.commit()

        result = await sync_system_agents_for_org(db, org_id)
        await db.commit()

        deep_researcher = await db.scalar(
            select(Agent).where(
                Agent.org_id == org_id,
                Agent.template_key == "deep-researcher",
            )
        )

    assert deep_researcher is None
    assert result.skipped >= 1
