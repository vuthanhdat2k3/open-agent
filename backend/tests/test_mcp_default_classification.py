"""Task 3 hardening — newly discovered MCP tools must fail closed.

`McpRepository.replace_tools` is the only place new `McpTool` rows are
created (it runs every time an MCP server is (re)connected and its tool
list is refreshed). An MCP server is a third-party integration outside
OpenAgent's control, so a tool it advertises must default to the most
restrictive classification - `dangerous` risk tier plus
`requires_approval=True` - until an admin explicitly reclassifies it.
Silently defaulting a new tool to `safe`/no-approval would let any MCP
server auto-grant itself unattended execution the moment it's connected.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.mcp import McpServer, McpTool
from app.repositories.mcp_repo import McpRepository


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_server(db: AsyncSession) -> McpServer:
    from app.models.organization import Organization

    org = Organization(name="MCP Default Org", slug="mcp-default-org")
    db.add(org)
    await db.commit()
    await db.refresh(org)

    server = McpServer(org_id=org.id, name="third-party", transport="stdio")
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def test_newly_discovered_tool_defaults_to_dangerous_and_requires_approval(
    async_session_factory,
) -> None:
    async with async_session_factory() as db:
        server = await _seed_server(db)
        repo = McpRepository(db)

        await repo.replace_tools(
            server.id,
            [{"name": "brand_new_tool", "description": "unknown", "input_schema": {}}],
        )

        tool = await db.scalar(
            select(McpTool).where(McpTool.server_id == server.id, McpTool.name == "brand_new_tool")
        )

    assert tool is not None
    assert tool.risk_tier == "dangerous"
    assert tool.requires_approval is True


async def test_reconnect_preserves_an_admin_reclassification(async_session_factory) -> None:
    """Re-syncing a server's tool list (every connect) must not silently
    reset a tool an admin already downgraded to safe/no-approval - that
    would force re-approval workflows to be redone forever."""
    async with async_session_factory() as db:
        server = await _seed_server(db)
        repo = McpRepository(db)

        await repo.replace_tools(
            server.id,
            [{"name": "reviewed_tool", "description": "v1", "input_schema": {}}],
        )
        reviewed = await db.scalar(
            select(McpTool).where(McpTool.server_id == server.id, McpTool.name == "reviewed_tool")
        )
        reviewed.risk_tier = "safe"
        reviewed.requires_approval = False
        await db.commit()

        # Server reconnects; the tool list comes back unchanged.
        await repo.replace_tools(
            server.id,
            [{"name": "reviewed_tool", "description": "v1", "input_schema": {}}],
        )

        after = await db.scalar(
            select(McpTool).where(McpTool.server_id == server.id, McpTool.name == "reviewed_tool")
        )

    assert after.risk_tier == "safe"
    assert after.requires_approval is False


async def test_reconnect_still_defaults_a_brand_new_tool_even_when_others_are_reviewed(
    async_session_factory,
) -> None:
    """A mixed reconnect (one reviewed tool, one never-seen-before tool) must
    default only the new one - the reviewed one's classification must not
    leak onto it, and the new one must not inherit a permissive default."""
    async with async_session_factory() as db:
        server = await _seed_server(db)
        repo = McpRepository(db)

        await repo.replace_tools(
            server.id,
            [{"name": "reviewed_tool", "description": "v1", "input_schema": {}}],
        )
        reviewed = await db.scalar(
            select(McpTool).where(McpTool.server_id == server.id, McpTool.name == "reviewed_tool")
        )
        reviewed.risk_tier = "safe"
        reviewed.requires_approval = False
        await db.commit()

        await repo.replace_tools(
            server.id,
            [
                {"name": "reviewed_tool", "description": "v1", "input_schema": {}},
                {"name": "second_new_tool", "description": "new", "input_schema": {}},
            ],
        )

        new_tool = await db.scalar(
            select(McpTool).where(McpTool.server_id == server.id, McpTool.name == "second_new_tool")
        )
        reviewed_after = await db.scalar(
            select(McpTool).where(McpTool.server_id == server.id, McpTool.name == "reviewed_tool")
        )

    assert new_tool.risk_tier == "dangerous"
    assert new_tool.requires_approval is True
    assert reviewed_after.risk_tier == "safe"
    assert reviewed_after.requires_approval is False
