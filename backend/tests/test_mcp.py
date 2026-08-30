from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.mcp import McpServer
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



def test_ci_rag_search_collection_is_scoped_to_current_org() -> None:
    from app.mcp.client import _rag_collection_scope_error

    assert _rag_collection_scope_error("rag_search", "ci-knowledge-org-a", "org-a") is None
    assert _rag_collection_scope_error("rag_search", "ci-knowledge-org-a", "org-b")
    assert _rag_collection_scope_error("rag_search", "ci-knowledge-org-a", None)
    assert _rag_collection_scope_error("rag_search", "default", "org-b") is None
    assert _rag_collection_scope_error("rag_ingest_text", "ci-knowledge-org-a", "org-b") is None



@pytest.mark.asyncio
async def test_mcp_run_rejects_cross_org_ci_collection_before_server_lookup() -> None:
    from app.core.tools.types import ToolContext
    from app.mcp.client import _make_mcp_run

    class UnusedDb:
        async def execute(self, _statement):
            raise AssertionError("cross-org collection must be rejected before DB lookup")

    run = _make_mcp_run("server-1", "rag_search")
    result = await run(
        {"query": "customer", "collection": "ci-knowledge-org-a"},
        ToolContext(db=UnusedDb(), org_id="org-b"),
    )

    assert result == "error: rag_search collection is not accessible for this organization"


# ---------------------------------------------------------------------------
# Generic RAG collection tenant-boundary namespacing (task 4 hardening)
# ---------------------------------------------------------------------------


def test_namespace_rag_collection_prefixes_generic_collections() -> None:
    from app.mcp.client import _namespace_rag_collection

    assert _namespace_rag_collection("default", "org-a") == "org-org-a-default"
    assert _namespace_rag_collection("my-docs", "org-a") == "org-org-a-my-docs"


def test_namespace_rag_collection_leaves_ci_knowledge_untouched() -> None:
    from app.mcp.client import _namespace_rag_collection

    assert _namespace_rag_collection("ci-knowledge-org-a", "org-a") == "ci-knowledge-org-a"
    # Even a CI collection belonging to a *different* org is left alone here:
    # rejecting cross-org CI access is _rag_collection_scope_error's job, and
    # that check always runs first in _make_mcp_run. This function must not
    # double-namespace a name that already carries the CI prefix.
    assert _namespace_rag_collection("ci-knowledge-org-b", "org-a") == "ci-knowledge-org-b"


def test_namespace_rag_collection_does_not_double_prefix() -> None:
    from app.mcp.client import _namespace_rag_collection

    already_namespaced = "org-org-a-default"
    assert _namespace_rag_collection(already_namespaced, "org-a") == already_namespaced


def test_namespace_rag_collection_is_a_noop_without_org_or_string() -> None:
    from app.mcp.client import _namespace_rag_collection

    assert _namespace_rag_collection("default", None) == "default"
    assert _namespace_rag_collection("default", "") == "default"
    assert _namespace_rag_collection(None, "org-a") is None
    assert _namespace_rag_collection(123, "org-a") == 123


def test_namespace_rag_collection_does_not_cross_prefix_between_orgs() -> None:
    """org-b's literal collection name must never resolve into org-a's
    namespace just because the string happens to start with 'org-'."""
    from app.mcp.client import _namespace_rag_collection

    assert _namespace_rag_collection("org-b-shared", "org-a") == "org-org-a-org-b-shared"


_RAG_LIST_SAMPLE = (
    "Collections (3):\n"
    "\n  org-org-a-default"
    "\n    Documents: 4  |  Chunks: 12  |  Created: 2024-01-01"
    "\n    Last updated: 2024-01-02"
    "\n  org-org-b-default"
    "\n    Documents: 1  |  Chunks: 3  |  Created: 2024-01-03"
    "\n    Last updated: 2024-01-04"
    "\n  ci-knowledge-org-a"
    "\n    Documents: 2  |  Chunks: 6  |  Created: 2024-01-05"
    "\n    Last updated: 2024-01-06"
)


def test_filter_rag_collections_output_hides_other_orgs() -> None:
    from app.mcp.client import _filter_rag_collections_output

    filtered = _filter_rag_collections_output(_RAG_LIST_SAMPLE, "org-a")

    assert "org-org-a-default" in filtered
    assert "ci-knowledge-org-a" in filtered
    assert "org-org-b-default" not in filtered
    assert filtered.startswith("Collections (2):")


def test_filter_rag_collections_output_empty_when_nothing_visible() -> None:
    from app.mcp.client import _filter_rag_collections_output

    only_other_org = (
        "Collections (1):\n"
        "\n  org-org-b-default"
        "\n    Documents: 1  |  Chunks: 3  |  Created: 2024-01-03"
        "\n    Last updated: 2024-01-04"
    )
    assert _filter_rag_collections_output(only_other_org, "org-a") == "No collections found."


def test_filter_rag_collections_output_is_a_noop_without_org_id() -> None:
    from app.mcp.client import _filter_rag_collections_output

    assert _filter_rag_collections_output(_RAG_LIST_SAMPLE, None) == _RAG_LIST_SAMPLE


def test_filter_rag_collections_output_ignores_non_listing_text() -> None:
    from app.mcp.client import _filter_rag_collections_output

    other_text = "No collections found."
    assert _filter_rag_collections_output(other_text, "org-a") == other_text


@pytest.mark.asyncio
async def test_mcp_run_namespaces_collection_argument_for_generic_rag_tools() -> None:
    """The exact args dict handed to McpManager.call_tool must carry the
    namespaced collection, and the original caller-supplied args must be
    left untouched (agent_loop/workflow engine may log/replay them)."""
    from app.core.tools.types import ToolContext
    from app.mcp.client import _make_mcp_run
    from app.models.mcp import McpServer

    captured: dict = {}

    class DummyClient:
        async def call_tool(self, server, name, args):
            captured["server"] = server
            captured["name"] = name
            captured["args"] = args
            return "ok"

    class FakeResult:
        def scalar_one_or_none(self):
            return McpServer(
                id="server-1",
                org_id="org-a",
                name="rag",
                connection_status="connected",
            )

    class FakeDb:
        async def execute(self, _statement):
            return FakeResult()

    import app.mcp.client as client_module

    client_module._MANAGER = DummyClient()  # type: ignore[assignment]
    try:
        run = _make_mcp_run("server-1", "rag_ingest_text")
        caller_args = {"text": "hello", "collection": "default"}
        result = await run(caller_args, ToolContext(db=FakeDb(), org_id="org-a"))
    finally:
        client_module._MANAGER = None

    assert result == "ok"
    assert captured["args"]["collection"] == "org-org-a-default"
    assert caller_args["collection"] == "default", "the caller's original dict must not be mutated"


@pytest.mark.asyncio
async def test_mcp_run_filters_rag_list_collections_result() -> None:
    from app.core.tools.types import ToolContext
    from app.mcp.client import _make_mcp_run
    from app.models.mcp import McpServer

    class DummyClient:
        async def call_tool(self, server, name, args):
            return _RAG_LIST_SAMPLE

    class FakeResult:
        def scalar_one_or_none(self):
            return McpServer(
                id="server-1",
                org_id="org-a",
                name="rag",
                connection_status="connected",
            )

    class FakeDb:
        async def execute(self, _statement):
            return FakeResult()

    import app.mcp.client as client_module

    client_module._MANAGER = DummyClient()  # type: ignore[assignment]
    try:
        run = _make_mcp_run("server-1", "rag_list_collections")
        result = await run({}, ToolContext(db=FakeDb(), org_id="org-a"))
    finally:
        client_module._MANAGER = None

    assert "org-org-a-default" in result
    assert "ci-knowledge-org-a" in result
    assert "org-org-b-default" not in result
