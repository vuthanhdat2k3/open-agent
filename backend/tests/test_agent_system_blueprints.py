"""Tests for 3-Source Merge Resolver, System Blueprints, and Fork-on-Write."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.agents.templates import SYSTEM_AGENT_BLUEPRINTS
from app.db.base import Base, gen_id
from app.models.model import Model
from app.models.org_agent_settings import OrgAgentSettings
from app.models.organization import Organization
from app.models.user import User
from app.services.agent_service import AgentService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def test_env(async_session_factory):
    async with async_session_factory() as db:
        org1 = Organization(id=gen_id(), name="Org 1", slug="org-1")
        org2 = Organization(id=gen_id(), name="Org 2", slug="org-2")
        user = User(id=gen_id(), email="admin@org1.com", hashed_password="pw", is_active=True)
        db.add(org1)
        db.add(org2)
        db.add(user)
        await db.flush()

        # Seed Provider
        from app.models.provider import Provider

        prov1 = Provider(
            id=gen_id(),
            org_id=org1.id,
            key="openai",
            name="OpenAI Provider",
            base_url="https://api.openai.com/v1",
        )
        db.add(prov1)
        await db.flush()

        # Seed an active model for org1
        model_fast = Model(
            id=gen_id(),
            org_id=org1.id,
            provider_id=prov1.id,
            name="gpt-4o-mini",
            display_name="GPT-4o Mini",
            tier="fast",
            active=True,
        )
        model_reasoning = Model(
            id=gen_id(),
            org_id=org1.id,
            provider_id=prov1.id,
            name="claude-3-5-sonnet",
            display_name="Claude 3.5 Sonnet",
            tier="reasoning",
            active=True,
        )
        db.add(model_fast)
        db.add(model_reasoning)
        await db.commit()

        yield {
            "org1_id": org1.id,
            "org2_id": org2.id,
            "user_id": user.id,
            "model_fast_id": model_fast.id,
            "model_reasoning_id": model_reasoning.id,
            "db": db,
        }


@pytest.mark.asyncio
async def test_zero_row_org_lists_all_13_blueprints(test_env):
    db = test_env["db"]
    service = AgentService(db)

    # Empty Org 1 should return all 13 Blueprints
    agents = await service.list(test_env["org1_id"])
    assert len(agents) == len(SYSTEM_AGENT_BLUEPRINTS)
    assert len(agents) == 13

    # Check that template keys and virtual IDs are correctly populated
    keys = {a.template_key for a in agents}
    assert keys == set(SYSTEM_AGENT_BLUEPRINTS.keys())
    assert all(a.is_customized is False for a in agents)

    # Primary agents are pinned by default
    general_agent = next(a for a in agents if a.template_key == "general")
    assert getattr(general_agent, "is_pinned", False) is True
    assert general_agent.model_id == test_env["model_fast_id"]


@pytest.mark.asyncio
async def test_get_by_id_and_key_resolver(test_env):
    db = test_env["db"]
    service = AgentService(db)

    # Get by deterministic ID
    agent_by_id = await service.get(test_env["org1_id"], "sys-agent-coder")
    assert agent_by_id is not None
    assert agent_by_id.template_key == "coder"
    assert agent_by_id.name == "Coder & UI Designer"

    # Get by template_key string
    agent_by_key = await service.get(test_env["org1_id"], "coder")
    assert agent_by_key is not None
    assert agent_by_key.id == "sys-agent-coder"


@pytest.mark.asyncio
async def test_fork_on_write_when_updating_system_blueprint(test_env):
    db = test_env["db"]
    service = AgentService(db)
    org1_id = test_env["org1_id"]
    org2_id = test_env["org2_id"]

    # Update system blueprint 'coder' for Org 1 (triggers fork-on-write)
    updated = await service.update(
        org1_id,
        "sys-agent-coder",
        {"system_prompt": "Custom specialized coder prompt for Org 1", "temperature": 0.1},
        test_env["user_id"],
    )
    assert updated.template_key == "coder"
    assert updated.is_customized is True
    assert updated.system_prompt == "Custom specialized coder prompt for Org 1"
    assert updated.temperature == 0.1

    # In Org 1, list() now returns 13 agents, with 'coder' coming from the DB override (no duplicate)
    org1_agents = await service.list(org1_id)
    assert len(org1_agents) == 13
    coder_org1 = next(a for a in org1_agents if a.template_key == "coder")
    assert coder_org1.id == updated.id
    assert coder_org1.is_customized is True

    # In Org 2, 'coder' remains a pure un-forked virtual blueprint
    org2_agents = await service.list(org2_id)
    assert len(org2_agents) == 13
    coder_org2 = next(a for a in org2_agents if a.template_key == "coder")
    assert coder_org2.id == "sys-agent-coder"
    assert coder_org2.is_customized is False


@pytest.mark.asyncio
async def test_org_agent_settings_cheap_override_no_fork(test_env):
    db = test_env["db"]
    service = AgentService(db)
    org1_id = test_env["org1_id"]

    # Insert a cheap pin & model override in org_agent_settings
    setting = OrgAgentSettings(
        org_id=org1_id,
        template_key="deep-researcher",
        is_pinned=True,
        is_enabled=True,
        model_override_id=test_env["model_reasoning_id"],
        temperature_override=0.5,
    )
    db.add(setting)
    await db.commit()

    # List agents should reflect the cheap override while keeping is_customized=False
    agents = await service.list(org1_id)
    deep_res = next(a for a in agents if a.template_key == "deep-researcher")
    assert getattr(deep_res, "is_pinned", False) is True
    assert deep_res.model_id == test_env["model_reasoning_id"]
    assert deep_res.temperature == 0.5
    assert deep_res.is_customized is False


@pytest.mark.asyncio
async def test_multi_org_independent_fork_and_id_resolution(test_env):
    db = test_env["db"]
    service = AgentService(db)
    org1_id = test_env["org1_id"]
    org2_id = test_env["org2_id"]

    # 1. Both Org 1 and Org 2 start with un-forked sys-agent-general
    a1_initial = await service.get(org1_id, "sys-agent-general")
    a2_initial = await service.get(org2_id, "sys-agent-general")
    assert a1_initial.id == "sys-agent-general"
    assert a2_initial.id == "sys-agent-general"
    assert a1_initial.is_customized is False
    assert a2_initial.is_customized is False

    # 2. Org 1 forks 'general' by updating system_prompt
    forked_org1 = await service.update(
        org1_id,
        "sys-agent-general",
        {"system_prompt": "Prompt customized specifically for Org 1"},
        test_env["user_id"],
    )
    # Forked row gets a unique UUID primary key (never collides with 'sys-agent-general' or other orgs)
    assert forked_org1.id != "sys-agent-general"
    assert len(forked_org1.id) >= 32
    assert forked_org1.is_customized is True
    assert forked_org1.system_prompt == "Prompt customized specifically for Org 1"

    # 3. Calling service.get(org1_id, "sys-agent-general") looks through and resolves Org 1's forked DB row
    resolved_org1 = await service.get(org1_id, "sys-agent-general")
    assert resolved_org1 is not None
    assert resolved_org1.id == forked_org1.id
    assert resolved_org1.is_customized is True
    assert resolved_org1.system_prompt == "Prompt customized specifically for Org 1"

    # 4. Calling service.get(org2_id, "sys-agent-general") still returns the pristine un-forked blueprint
    resolved_org2 = await service.get(org2_id, "sys-agent-general")
    assert resolved_org2 is not None
    assert resolved_org2.id == "sys-agent-general"
    assert resolved_org2.is_customized is False

    # 5. Org 2 now ALSO forks 'general' with a different prompt
    # Seed active model for org2
    from app.models.provider import Provider

    prov2 = Provider(
        id=gen_id(),
        org_id=org2_id,
        key="openai",
        name="OpenAI Provider Org 2",
        base_url="https://api.openai.com/v1",
    )
    db.add(prov2)
    await db.flush()

    model_org2 = Model(
        id=gen_id(),
        org_id=org2_id,
        provider_id=prov2.id,
        name="gpt-4o",
        display_name="GPT-4o",
        tier="fast",
        active=True,
    )
    db.add(model_org2)
    await db.commit()

    forked_org2 = await service.update(
        org2_id,
        "sys-agent-general",
        {"system_prompt": "Prompt customized specifically for Org 2"},
        test_env["user_id"],
    )
    # Org 2 gets its own unique UUID primary key distinct from Org 1 (NO PK collision)
    assert forked_org2.id != "sys-agent-general"
    assert forked_org2.id != forked_org1.id
    assert forked_org2.is_customized is True
    assert forked_org2.system_prompt == "Prompt customized specifically for Org 2"

    # 6. Verify each org resolves its own distinct forked agent via "sys-agent-general"
    org1_final = await service.get(org1_id, "sys-agent-general")
    org2_final = await service.get(org2_id, "sys-agent-general")
    assert org1_final.id == forked_org1.id
    assert org2_final.id == forked_org2.id
    assert org1_final.system_prompt == "Prompt customized specifically for Org 1"
    assert org2_final.system_prompt == "Prompt customized specifically for Org 2"
