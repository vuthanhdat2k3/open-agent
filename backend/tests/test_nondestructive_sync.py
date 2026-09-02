from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.agents.sync import sync_system_agents_all_orgs
from app.core.providers.sync import sync_system_providers_all_orgs
from app.core.workflow.sync import sync_system_workflow_templates
from app.core.workflow.templates import SYSTEM_WORKFLOW_BLUEPRINTS
from app.db.base import Base, gen_id
from app.models.agent import Agent
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.workflow import Workflow
from app.models.workflow_template import WorkflowTemplate
from app.services.agent_service import AgentService
from app.services.workflow_service import WorkflowService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_sync_preserves_existing_customizations(async_session_factory) -> None:
    async with async_session_factory() as db:
        org = Organization(id=gen_id(), name="Custom Org", slug="custom-org")
        db.add(org)
        await db.commit()

        # Seed an existing customized provider
        custom_provider = Provider(
            id=gen_id(),
            org_id=org.id,
            key="openai",
            name="My Custom OpenAI Proxy",
            base_url="https://custom.proxy/v1",
            normalized_base_url="https://custom.proxy/v1",
            template_key="openai",
            api_key="sk-custom-secret",
            is_default=True,
            status="ready",
        )
        custom_model = Model(
            id=gen_id(),
            org_id=org.id,
            provider_id=custom_provider.id,
            name="gpt-4o-custom",
            display_name="GPT-4o Custom Special",
            tier="frontier",
            active=True,
            enabled=True,
        )
        db.add(custom_provider)
        db.add(custom_model)
        await db.commit()

        # Run provider sync
        results = await sync_system_providers_all_orgs(db)
        assert len(results) == 1
        assert results[0].skipped >= 1

        # Verify custom provider properties were preserved 100%
        refreshed = await db.scalar(
            select(Provider).where(Provider.org_id == org.id, Provider.key == "openai")
        )
        assert refreshed is not None
        assert refreshed.name == "My Custom OpenAI Proxy"
        assert refreshed.base_url == "https://custom.proxy/v1"
        assert refreshed.is_default is True

        # Verify missing provider templates were added for the org without overwriting custom
        gemini = await db.scalar(
            select(Provider).where(Provider.org_id == org.id, Provider.key == "gemini")
        )
        assert gemini is not None
        assert gemini.name == "Google Gemini"
        assert gemini.is_default is False  # Didn't overwrite existing default


@pytest.mark.asyncio
async def test_workflow_template_sync_restores_published_status(async_session_factory) -> None:
    async with async_session_factory() as db:
        # First sync to populate
        await sync_system_workflow_templates(db)

        # Archive all system templates
        templates = (await db.scalars(select(WorkflowTemplate))).all()
        assert len(templates) >= len(SYSTEM_WORKFLOW_BLUEPRINTS)
        for t in templates:
            t.status = "archived"
        await db.commit()

        # Re-run sync
        await sync_system_workflow_templates(db)

        # Verify all system templates were restored to published
        refreshed = (await db.scalars(select(WorkflowTemplate))).all()
        for t in refreshed:
            if t.key in SYSTEM_WORKFLOW_BLUEPRINTS:
                assert t.status == "published", f"Template {t.key} was not restored to published"


@pytest.mark.asyncio
async def test_workflow_update_sets_is_customized(async_session_factory) -> None:
    async with async_session_factory() as db:
        org = Organization(id=gen_id(), name="WF Org", slug="wf-org")
        db.add(org)
        await db.commit()

        wf = Workflow(
            id=gen_id(),
            org_id=org.id,
            name="Morning Command Center",
            description="Default description",
            graph={"nodes": [], "edges": []},
            template_key="morning-command-center",
            is_customized=False,
        )
        db.add(wf)
        await db.commit()

        # Update the workflow
        service = WorkflowService(db)
        updated = await service.update(org.id, wf.id, {"name": "My Tailored Morning Flow"})
        assert updated.name == "My Tailored Morning Flow"
        assert updated.is_customized is True


@pytest.mark.asyncio
async def test_agent_update_sets_is_customized_and_preserves_on_sync(async_session_factory) -> None:
    async with async_session_factory() as db:
        org = Organization(id=gen_id(), name="Agent Org", slug="agent-org")
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
            enabled=True,
        )
        db.add(org)
        db.add(provider)
        db.add(model)
        await db.commit()

        # Startup sync creates pristine system agents
        await sync_system_agents_all_orgs(db)

        coder = await db.scalar(
            select(Agent).where(Agent.org_id == org.id, Agent.template_key == "coder")
        )
        assert coder is not None
        assert coder.is_customized is False

        # User customizes the coder agent
        service = AgentService(db)
        custom_prompt = "You are a Rust specialist exclusively focusing on async-std."
        updated = await service.update(org.id, coder.id, {"system_prompt": custom_prompt})
        assert updated.is_customized is True

        # Re-run startup sync
        await sync_system_agents_all_orgs(db)

        # Verify user customization was preserved 100%!
        refreshed = await db.scalar(
            select(Agent).where(Agent.org_id == org.id, Agent.template_key == "coder")
        )
        assert refreshed is not None
        assert refreshed.system_prompt == custom_prompt
        assert refreshed.is_customized is True
