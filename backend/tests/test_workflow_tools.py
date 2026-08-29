"""Unit tests for Workflow management tools."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.tools.registry import BUILTIN_TOOLS
from app.core.tools.types import ToolContext
from app.db.base import Base, gen_id, utc_now
from app.models.organization import Organization
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateVersion


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
        org = Organization(id=gen_id(), name="Test Org", slug="test-org")
        user = User(id=gen_id(), email="user@test.com", hashed_password="pw", is_active=True)
        db.add(org)
        db.add(user)
        await db.commit()

        # Seed a test workflow
        wf = Workflow(
            id=gen_id(),
            org_id=org.id,
            created_by_user_id=user.id,
            name="Daily News Digest",
            description="Fetch daily news and summarize",
            graph={
                "nodes": [
                    {"id": "input-1", "kind": "input", "label": "Start"},
                    {"id": "output-1", "kind": "output", "label": "End"},
                ],
                "edges": [{"from_": "input-1", "to": "output-1"}],
            },
        )
        db.add(wf)

        # Seed a marketplace template
        tpl = WorkflowTemplate(
            id=gen_id(),
            key="news-digest",
            status="published",
        )
        db.add(tpl)
        version = WorkflowTemplateVersion(
            id=gen_id(),
            template_id=tpl.id,
            version=1,
            name="News Digest Template",
            category="custom",
            description="Marketplace template for news",
            outcome="Daily news report",
            published_at=utc_now(),
        )
        db.add(version)
        await db.commit()

        yield {
            "org_id": org.id,
            "user_id": user.id,
            "workflow_id": wf.id,
            "template_key": tpl.key,
            "db": db,
        }


@pytest.mark.asyncio
async def test_workflow_tools_registered():
    expected_tools = [
        "workflow_list",
        "workflow_get",
        "workflow_run",
        "workflow_create",
        "workflow_update",
        "workflow_delete",
        "workflow_generate",
        "workflow_catalog_list",
        "workflow_catalog_install",
    ]
    for tool_name in expected_tools:
        assert tool_name in BUILTIN_TOOLS, f"Tool '{tool_name}' must be registered in BUILTIN_TOOLS"


@pytest.mark.asyncio
async def test_workflow_list_and_get(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # Test workflow_list
    list_tool = BUILTIN_TOOLS["workflow_list"]
    res_str = await list_tool.run({}, ctx)
    res = json.loads(res_str)
    assert res["count"] >= 1
    assert any(w["name"] == "Daily News Digest" for w in res["workflows"])

    # Test workflow_get by ID
    get_tool = BUILTIN_TOOLS["workflow_get"]
    get_str = await get_tool.run({"workflow_id": test_env["workflow_id"]}, ctx)
    get_res = json.loads(get_str)
    assert get_res["id"] == test_env["workflow_id"]
    assert get_res["name"] == "Daily News Digest"
    assert len(get_res["graph"]["nodes"]) == 2


@pytest.mark.asyncio
async def test_workflow_create_update_delete(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # Test workflow_create
    create_tool = BUILTIN_TOOLS["workflow_create"]
    create_str = await create_tool.run(
        {
            "name": "Customer Support Pipeline",
            "description": "Auto-respond to tickets",
            "graph": {
                "nodes": [
                    {"id": "in-1", "kind": "input", "label": "Receive Ticket"},
                    {"id": "out-1", "kind": "output", "label": "Respond"},
                ],
                "edges": [{"from_": "in-1", "to": "out-1"}],
            },
        },
        ctx,
    )
    created = json.loads(create_str)
    assert created["status"] == "created"
    new_id = created["id"]
    assert new_id is not None

    # Test workflow_update
    update_tool = BUILTIN_TOOLS["workflow_update"]
    update_str = await update_tool.run(
        {
            "workflow_id": new_id,
            "name": "Updated Customer Support Pipeline",
            "description": "Updated description",
        },
        ctx,
    )
    updated = json.loads(update_str)
    assert updated["status"] == "updated"
    assert updated["name"] == "Updated Customer Support Pipeline"

    # Test workflow_delete
    delete_tool = BUILTIN_TOOLS["workflow_delete"]
    del_res = await delete_tool.run({"workflow_id": new_id}, ctx)
    assert "Successfully deleted" in del_res


@pytest.mark.asyncio
async def test_workflow_catalog_list_and_install(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # Test catalog list
    cat_list = BUILTIN_TOOLS["workflow_catalog_list"]
    cat_str = await cat_list.run({}, ctx)
    cat_res = json.loads(cat_str)
    assert cat_res["count"] >= 1
    assert any(t["key"] == "news-digest" for t in cat_res["templates"])

    # Test catalog install
    install_tool = BUILTIN_TOOLS["workflow_catalog_install"]
    inst_str = await install_tool.run({"template_key": "news-digest"}, ctx)
    inst_res = json.loads(inst_str)
    assert inst_res["status"] == "installed"
    assert inst_res["workflow_id"] is not None
