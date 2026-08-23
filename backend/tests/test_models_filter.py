from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base, gen_id
from app.models.model import Model
from app.models.provider import Provider
from app.services.model_service import ModelService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_model_filtering(db_session: AsyncSession):
    org_id = gen_id()
    p1 = Provider(id=gen_id(), org_id=org_id, key="openai", name="OpenAI", base_url="https://api.openai.com/v1")
    p2 = Provider(id=gen_id(), org_id=org_id, key="anthropic", name="Anthropic", base_url="https://api.anthropic.com/v1")
    db_session.add_all([p1, p2])
    await db_session.flush()

    m1 = Model(
        id=gen_id(),
        org_id=org_id,
        provider_id=p1.id,
        name="gpt-4o",
        display_name="GPT-4o",
        enabled=True,
        active=True,
    )
    m2 = Model(
        id=gen_id(),
        org_id=org_id,
        provider_id=p1.id,
        name="gpt-3.5-turbo",
        display_name="GPT-3.5 Turbo",
        enabled=False,
        active=False,
    )
    m3 = Model(
        id=gen_id(),
        org_id=org_id,
        provider_id=p2.id,
        name="claude-3-5-sonnet",
        display_name="Claude 3.5 Sonnet",
        enabled=True,
        active=True,
    )
    db_session.add_all([m1, m2, m3])
    await db_session.commit()

    service = ModelService(db_session)

    # 1. Filter by active=True
    active_models = await service.list(org_id, active=True)
    assert len(active_models) == 2
    assert {m.name for m in active_models} == {"gpt-4o", "claude-3-5-sonnet"}

    # 2. Filter by active=False
    inactive_models = await service.list(org_id, active=False)
    assert len(inactive_models) == 1
    assert inactive_models[0].name == "gpt-3.5-turbo"

    # 3. Filter by provider_id
    openai_models = await service.list(org_id, provider_id=p1.id, with_inactive=True)
    assert len(openai_models) == 2
    assert {m.name for m in openai_models} == {"gpt-4o", "gpt-3.5-turbo"}

    # 4. Filter by provider key
    anthropic_models = await service.list(org_id, provider_id="anthropic", with_inactive=True)
    assert len(anthropic_models) == 1
    assert anthropic_models[0].name == "claude-3-5-sonnet"

    # 5. Combined filter: provider openai + active=True
    openai_active = await service.list(org_id, provider_id=p1.id, active=True)
    assert len(openai_active) == 1
    assert openai_active[0].name == "gpt-4o"
