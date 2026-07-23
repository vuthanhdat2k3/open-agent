from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.agent import Agent
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.repositories.agent_repo import AgentRepository
from app.repositories.model_repo import ModelRepository
from app.repositories.org_repo import OrganizationRepository
from app.repositories.provider_repo import ProviderRepository


async def test_repository_org_scoping_and_isolation() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        org_repo = OrganizationRepository(session)
        provider_repo = ProviderRepository(session)
        model_repo = ModelRepository(session)
        agent_repo = AgentRepository(session)

        # Create two orgs
        org_a = await org_repo.create(Organization(name="Org A", slug="org-a"))
        org_b = await org_repo.create(Organization(name="Org B", slug="org-b"))

        # Create provider & model for org_a and org_b
        p_a = await provider_repo.create(
            Provider(org_id=org_a.id, key="p-a", name="p-a", base_url="http://a")
        )
        m_a = await model_repo.create(
            Model(org_id=org_a.id, provider_id=p_a.id, name="m-a", display_name="Model A")
        )

        p_b = await provider_repo.create(
            Provider(org_id=org_b.id, key="p-b", name="p-b", base_url="http://b")
        )
        m_b = await model_repo.create(
            Model(org_id=org_b.id, provider_id=p_b.id, name="m-b", display_name="Model B")
        )

        # Create agent_a in org_a and agent_b in org_b
        agent_a = await agent_repo.create(
            Agent(
                org_id=org_a.id,
                name="Agent A",
                system_prompt="prompt a",
                model_id=m_a.id,
            )
        )
        agent_b = await agent_repo.create(
            Agent(
                org_id=org_b.id,
                name="Agent B",
                system_prompt="prompt b",
                model_id=m_b.id,
            )
        )

        # List org_a agents -> only agent_a
        agents_a = await agent_repo.list(org_id=org_a.id)
        assert len(agents_a) == 1
        assert agents_a[0].id == agent_a.id
        assert agents_a[0].name == "Agent A"

        # List org_b agents -> only agent_b
        agents_b = await agent_repo.list(org_id=org_b.id)
        assert len(agents_b) == 1
        assert agents_b[0].id == agent_b.id

        # Cross-tenant GET: org_a tries to get agent_b -> returns None
        cross_get = await agent_repo.get(org_id=org_a.id, id=agent_b.id)
        assert cross_get is None

        # Cross-tenant DELETE: org_a tries to delete agent_b -> returns False
        deleted = await agent_repo.delete(org_id=org_a.id, id=agent_b.id)
        assert deleted is False

        # Verify agent_b still exists for org_b
        still_b = await agent_repo.get(org_id=org_b.id, id=agent_b.id)
        assert still_b is not None

        # TypeError if org_id is missing/empty
        with pytest.raises(TypeError, match="org_id is required"):
            await agent_repo.list(org_id="")

        with pytest.raises(TypeError, match="org_id is required"):
            await agent_repo.get(org_id="", id=agent_a.id)

    await engine.dispose()


async def test_same_name_across_different_orgs() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        org_repo = OrganizationRepository(session)
        provider_repo = ProviderRepository(session)
        model_repo = ModelRepository(session)
        agent_repo = AgentRepository(session)

        org_a = await org_repo.create(Organization(name="Org A", slug="org-a"))
        org_b = await org_repo.create(Organization(name="Org B", slug="org-b"))

        p_a = await provider_repo.create(
            Provider(org_id=org_a.id, key="openai", name="OpenAI", base_url="http://a")
        )
        p_b = await provider_repo.create(
            Provider(org_id=org_b.id, key="openai", name="OpenAI", base_url="http://b")
        )
        assert p_a.id != p_b.id

        m_a = await model_repo.create(
            Model(org_id=org_a.id, provider_id=p_a.id, name="gpt-4o", display_name="GPT-4o")
        )
        m_b = await model_repo.create(
            Model(org_id=org_b.id, provider_id=p_b.id, name="gpt-4o", display_name="GPT-4o")
        )

        agent_a = await agent_repo.create(
            Agent(org_id=org_a.id, name="Assistant", system_prompt="a", model_id=m_a.id)
        )
        agent_b = await agent_repo.create(
            Agent(org_id=org_b.id, name="Assistant", system_prompt="b", model_id=m_b.id)
        )
        assert agent_a.id != agent_b.id

    await engine.dispose()
