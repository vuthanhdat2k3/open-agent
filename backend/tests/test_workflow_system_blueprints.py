from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.workflow.templates import SYSTEM_WORKFLOW_BLUEPRINTS
from app.db.base import Base, gen_id
from app.models.organization import Organization
from app.models.user import User
from app.schemas.workflow import WorkflowOut
from app.services.workflow_service import WorkflowService


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession) -> Organization:
    org = Organization(id=gen_id(), name="Workflow Test Org", slug="workflow-test-org")
    db_session.add(org)
    await db_session.commit()
    return org


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_org: Organization) -> User:
    user = User(
        id=gen_id(),
        email="test_workflow_user@example.com",
        hashed_password="pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_zero_row_org_lists_all_7_workflow_blueprints(
    db_session: AsyncSession, test_org: Organization
):
    """An organization with 0 DB workflows automatically sees all 7 system blueprints."""
    service = WorkflowService(db_session)
    workflows = await service.list(test_org.id)

    assert len(workflows) == 7
    for wf in workflows:
        assert wf.template_key in SYSTEM_WORKFLOW_BLUEPRINTS
        assert wf.is_customized is False
        assert wf.id == f"sys-wf-{wf.template_key}"
        # Validate Pydantic schema serialization
        out = WorkflowOut.model_validate(wf)
        assert out.template_key == wf.template_key
        assert out.is_customized is False


@pytest.mark.asyncio
async def test_get_workflow_by_id_and_key_resolver(
    db_session: AsyncSession, test_org: Organization
):
    """WorkflowService.get resolves by sys-wf-* ID, template key, and exact name."""
    service = WorkflowService(db_session)

    # 1. By virtual ID
    wf1 = await service.get(test_org.id, "sys-wf-morning-command-center")
    assert wf1 is not None
    assert wf1.template_key == "morning-command-center"

    # 2. By template key
    wf2 = await service.get(test_org.id, "morning-command-center")
    assert wf2 is not None
    assert wf2.template_key == "morning-command-center"

    # 3. By exact name
    wf3 = await service.get(test_org.id, "Morning Command Center")
    assert wf3 is not None
    assert wf3.template_key == "morning-command-center"


@pytest.mark.asyncio
async def test_workflow_fork_on_write_when_updating(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Updating a virtual blueprint creates a real DB row for the org (Fork-on-Write)."""
    service = WorkflowService(db_session)

    updated_graph = {
        "nodes": [
            {"id": "input", "kind": "input", "label": "Start", "parameters": {}},
            {"id": "output", "kind": "output", "label": "Finish", "parameters": {}},
        ],
        "edges": [{"from_": "input", "to": "output"}],
    }

    updated = await service.update(
        test_org.id,
        "sys-wf-morning-command-center",
        {
            "name": "Customized Morning Command Center",
            "description": "Org customized version",
            "graph": updated_graph,
        },
        user_id=test_user.id,
    )

    assert updated.id != "sys-wf-morning-command-center"
    assert len(updated.id) == 32  # hex UUID
    assert updated.template_key == "morning-command-center"
    assert updated.is_customized is True
    assert updated.name == "Customized Morning Command Center"

    # List should still return 7 items total, with the forked one replacing the virtual one
    workflows = await service.list(test_org.id)
    assert len(workflows) == 7

    forked_in_list = [w for w in workflows if w.template_key == "morning-command-center"][0]
    assert forked_in_list.id == updated.id
    assert forked_in_list.is_customized is True
    assert forked_in_list.name == "Customized Morning Command Center"


@pytest.mark.asyncio
async def test_multi_org_independent_workflow_fork(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Org A and Org B fork the same template independently with zero PK collision or bleed."""
    org_b = Organization(id=gen_id(), name="Org B", slug="org-b")
    db_session.add(org_b)
    await db_session.commit()

    service = WorkflowService(db_session)

    # Org A forks
    wf_a = await service.update(
        test_org.id,
        "sys-wf-follow-up-radar",
        {"name": "Org A Radar"},
        user_id=test_user.id,
    )

    # Org B forks
    wf_b = await service.update(
        org_b.id,
        "sys-wf-follow-up-radar",
        {"name": "Org B Radar"},
        user_id=test_user.id,
    )

    assert wf_a.id != wf_b.id
    assert wf_a.org_id == test_org.id
    assert wf_b.org_id == org_b.id
    assert wf_a.name == "Org A Radar"
    assert wf_b.name == "Org B Radar"


@pytest.mark.asyncio
async def test_repeated_update_on_forked_workflow_no_duplicate(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Repeated updates on an already-forked workflow update in-place without duplicate rows."""
    service = WorkflowService(db_session)

    # First update: fork-on-write creates DB row
    wf1 = await service.update(
        test_org.id,
        "sys-wf-meeting-preparation",
        {"name": "Meeting Prep V1"},
        user_id=test_user.id,
    )
    first_id = wf1.id

    # Second update using DB ID
    wf2 = await service.update(
        test_org.id,
        first_id,
        {"name": "Meeting Prep V2"},
        user_id=test_user.id,
    )
    assert wf2.id == first_id
    assert wf2.name == "Meeting Prep V2"

    # Third update using blueprint key
    wf3 = await service.update(
        test_org.id,
        "sys-wf-meeting-preparation",
        {"name": "Meeting Prep V3"},
        user_id=test_user.id,
    )
    assert wf3.id == first_id
    assert wf3.name == "Meeting Prep V3"

    # Total workflows count remains exactly 7
    workflows = await service.list(test_org.id)
    assert len(workflows) == 7


@pytest.mark.asyncio
async def test_reset_workflow_to_template(
    db_session: AsyncSession, test_org: Organization, test_user: User
):
    """Resetting a forked workflow deletes the DB override and returns pristine blueprint."""
    service = WorkflowService(db_session)

    # Fork
    forked = await service.update(
        test_org.id,
        "sys-wf-end-of-day-client-digest",
        {"name": "Customized EOD Digest"},
        user_id=test_user.id,
    )
    assert forked.is_customized is True

    # Reset
    pristine = await service.reset_to_template(test_org.id, forked.id)
    assert pristine.id == "sys-wf-end-of-day-client-digest"
    assert pristine.is_customized is False
    assert pristine.name == "End-of-day Client Digest"

    # Check DB: record is gone
    workflows = await service.list(test_org.id)
    assert len(workflows) == 7
    eod = [w for w in workflows if w.template_key == "end-of-day-client-digest"][0]
    assert eod.is_customized is False
