from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base, gen_id
from app.main import app
from app.models.membership import Membership
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.role import Role
from app.models.user import User
from app.services.agent_service import AgentService
from app.services.model_service import ModelService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def env_setup(async_session_factory):
    async with async_session_factory() as db:
        org = Organization(id=gen_id(), name="Test Org", slug="test-org")
        user = User(id=gen_id(), email="admin@test.com", hashed_password="pw", is_active=True)
        db.add(org)
        db.add(user)
        await db.flush()

        membership = Membership(
            id=gen_id(),
            org_id=org.id,
            user_id=user.id,
            role=Role.org_admin,
            lifecycle_status="active",
        )
        db.add(membership)

        prov = Provider(
            id=gen_id(),
            org_id=org.id,
            key="openai",
            name="OpenAI",
            base_url="https://api.openai.com/v1",
        )
        db.add(prov)
        await db.flush()

        # Seed 3 models for 3 tiers
        m_economy = Model(
            id=gen_id(),
            org_id=org.id,
            provider_id=prov.id,
            name="gpt-4o-mini",
            display_name="GPT-4o Mini",
            tier="economy",
            active=True,
            enabled=True,
        )
        m_balanced = Model(
            id=gen_id(),
            org_id=org.id,
            provider_id=prov.id,
            name="gpt-4o",
            display_name="GPT-4o",
            tier="balanced",
            active=True,
            enabled=True,
        )
        m_frontier = Model(
            id=gen_id(),
            org_id=org.id,
            provider_id=prov.id,
            name="o3-mini",
            display_name="o3-mini",
            tier="frontier",
            active=True,
            enabled=True,
        )
        # Seed an alternative frontier model
        m_frontier_custom = Model(
            id=gen_id(),
            org_id=org.id,
            provider_id=prov.id,
            name="claude-3-5-sonnet",
            display_name="Claude 3.5 Sonnet",
            tier="frontier",
            active=True,
            enabled=True,
        )
        db.add_all([m_economy, m_balanced, m_frontier, m_frontier_custom])
        await db.commit()

        return {
            "db": db,
            "session_factory": async_session_factory,
            "org_id": org.id,
            "user_id": user.id,
            "m_economy": m_economy,
            "m_balanced": m_balanced,
            "m_frontier": m_frontier,
            "m_frontier_custom": m_frontier_custom,
        }


@pytest.mark.asyncio
async def test_agent_service_tier_resolution_priority(env_setup):
    db = env_setup["db"]
    org_id = env_setup["org_id"]
    agent_svc = AgentService(db)
    model_svc = ModelService(db)

    # 1. Default tier resolution (no org_model_tier_config)
    # General assistant (recommended_tier: fast -> economy) -> m_economy
    general_model = await agent_svc._resolve_model_for_tier(org_id, "fast")
    assert general_model == env_setup["m_economy"].id

    # Deep researcher (recommended_tier: reasoning -> frontier) -> m_frontier
    researcher_model = await agent_svc._resolve_model_for_tier(org_id, "reasoning")
    assert researcher_model == env_setup["m_frontier"].id

    # 2. Set Org Model Tier Config override for 'frontier' to m_frontier_custom
    await model_svc.set_tier_matrix(
        org_id,
        {"frontier": env_setup["m_frontier_custom"].id},
    )

    # Now frontier resolution resolves to the configured override
    updated_frontier = await agent_svc._resolve_model_for_tier(org_id, "reasoning")
    assert updated_frontier == env_setup["m_frontier_custom"].id

    # Economy resolution remains unaffected
    assert await agent_svc._resolve_model_for_tier(org_id, "fast") == env_setup["m_economy"].id

    # 3. Check virtual agent list reflecting the tier matrix
    agents = await agent_svc.list(org_id)
    deep_web = next(a for a in agents if a.template_key == "deep-researcher")
    assert deep_web.model_id == env_setup["m_frontier_custom"].id


@pytest.mark.asyncio
async def test_tier_matrix_api_routes(env_setup):
    from app.dependencies import get_current_org_id, get_current_user, get_db

    session_factory = env_setup["session_factory"]
    org_id = env_setup["org_id"]
    user_id = env_setup["user_id"]

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_current_user():
        async with session_factory() as session:
            return await session.get(User, user_id)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_org_id] = lambda: org_id
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # GET /api/models/tier-matrix
        res = await ac.get("/api/models/tier-matrix")
        assert res.status_code == 200, res.text
        data = res.json()
        assert "tiers" in data
        assert data["tiers"]["economy"]["id"] == env_setup["m_economy"].id
        assert data["tiers"]["balanced"]["id"] == env_setup["m_balanced"].id
        assert data["tiers"]["frontier"]["id"] in (env_setup["m_frontier"].id, env_setup["m_frontier_custom"].id)

        # PUT /api/models/tier-matrix
        update_res = await ac.put(
            "/api/models/tier-matrix",
            json={
                "tier_mappings": {
                    "frontier": env_setup["m_frontier_custom"].id,
                    "economy": env_setup["m_economy"].id,
                    "balanced": env_setup["m_balanced"].id,
                }
            },
        )
        assert update_res.status_code == 200, update_res.text
        updated_data = update_res.json()
        assert updated_data["tiers"]["frontier"]["id"] == env_setup["m_frontier_custom"].id

    app.dependency_overrides.clear()
