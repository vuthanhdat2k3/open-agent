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
        org1 = Organization(id=gen_id(), name="Org 1")
        org2 = Organization(id=gen_id(), name="Org 2")
        user = User(id=gen_id(), email="admin@org1.com", hashed_password="pw", is_active=True)
        db.add(org1)
        db.add(org2)
        db.add(user)
        await db.flush()

        # Seed an active model for org1
        model_fast = Model(
            id=gen_id(),
            org_id=org1.id,
            name="gpt-4o-mini",
            provider="openai",
            tier="fast",
            active=True,
        )
        model_reasoning = Model(
            id=gen_id(),
            org_id=org1.id,
            name="claude-3-5-sonnet",
            provider="anthropic",
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
