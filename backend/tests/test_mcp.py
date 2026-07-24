from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.mcp import McpServer, McpTool
from app.services.mcp_service import McpService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


class DummyMcpManager:
    def __init__(self):
        self.connected_ids = set()
        self.disconnected_ids = set()

    async def connect(self, server: McpServer):
        self.connected_ids.add(server.id)

    async def disconnect(self, server_id: str):
        self.disconnected_ids.add(server_id)

    def get(self, server: McpServer):
        class DummyClient:
            async def list_tools(self):
                return [
                    {
                        "name": "drive_search",
                        "description": "Search files",
                        "input_schema": {"type": "object"},
                    }
                ]

        return DummyClient()


@pytest.mark.asyncio
async def test_mcp_service_crud_and_connect(async_session_factory, monkeypatch):
    dummy_mgr = DummyMcpManager()
    monkeypatch.setattr("app.services.mcp_service.get_mcp_manager", lambda: dummy_mgr)

    async with async_session_factory() as db:
        service = McpService(db)
        org_id = "test-org-mcp"

        # Create
        server = await service.create(
            org_id,
            {
                "name": "gdrive",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_drive_server"],
            },
        )
        assert server.id
        assert server.name == "gdrive"
        assert server.connection_status == "disconnected"

        # List
        servers = await service.list(org_id)
        assert len(servers) == 1
        assert servers[0].id == server.id

        # Connect
        res = await service.connect(org_id, server.id)
        assert res["ok"] is True
        assert res["tool_count"] == 1
        assert server.id in dummy_mgr.connected_ids

        # Verify tool saved
        updated = await service.get(org_id, server.id)
        assert updated.connection_status == "connected"
        assert len(updated.tools) == 1
        assert updated.tools[0].name == "drive_search"

        # Disconnect
        disc_res = await service.disconnect(org_id, server.id)
        assert disc_res["ok"] is True
        assert server.id in dummy_mgr.disconnected_ids

        # Delete
        del_res = await service.delete(org_id, server.id)
        assert del_res is True
        assert await service.get(org_id, server.id) is None
