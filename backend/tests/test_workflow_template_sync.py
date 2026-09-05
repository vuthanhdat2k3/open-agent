import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.sync import sync_system_workflow_templates
from app.core.workflow.templates import SYSTEM_WORKFLOW_BLUEPRINTS
from app.db.base import Base
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateVersion


@pytest.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_sync_system_workflow_templates(async_session: AsyncSession):
    # Ensure sync runs cleanly on empty DB
    await sync_system_workflow_templates(async_session)

    templates = (await async_session.execute(select(WorkflowTemplate))).scalars().all()
    assert len(templates) >= len(SYSTEM_WORKFLOW_BLUEPRINTS)

    versions = (await async_session.execute(select(WorkflowTemplateVersion))).scalars().all()
    assert len(versions) >= len(SYSTEM_WORKFLOW_BLUEPRINTS)

    # Verify idempotency
    await sync_system_workflow_templates(async_session)
    templates2 = (await async_session.execute(select(WorkflowTemplate))).scalars().all()
    assert len(templates2) == len(templates)
