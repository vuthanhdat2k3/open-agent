"""MCP server for the RAG service.

Exposes RAG capabilities (search, ingest, collection management, document
deletion) as MCP tools consumable by any MCP-compatible client (open-agent).

The default implementation uses :class:`mcp.server.fastmcp.FastMCP`.  If that
import is unavailable we fall back to the lower-level ``mcp.server.Server`` with
manual ``list_tools`` / ``call_tool`` handlers that dispatch to the same
implementation functions.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from rag_service.config import settings
from rag_service.core.logging import logger
from rag_service.db.base import get_sessionmaker
from rag_service.dependencies import get_components

try:  # pragma: no cover - fast path
    from mcp.server.fastmcp import FastMCP

    _HAS_FASTMCP = True
except Exception:  # pragma: no cover - optional dependency
    FastMCP = None  # type: ignore[assignment]
    _HAS_FASTMCP = False


# --------------------------------------------------------------------------- #
# Session helper
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _session() -> AsyncIterator[tuple[Any, Any]]:
    """Yield ``(AsyncSession, RAGComponents)`` inside a managed transaction."""
    async with get_sessionmaker()() as session:
        try:
            yield session, get_components()
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --------------------------------------------------------------------------- #
# Shared tool implementations (used by both FastMCP and the low-level fallback)
# --------------------------------------------------------------------------- #
async def _rag_search(
    query: str,
    collection: str = "default",
    top_k: int = 5,
    filters: dict | None = None,
    enable_graph: bool = False,
) -> str:
    try:
        from rag_service.services.retrieval_service import RetrievalService

        async with _session() as (session, comp):
            svc = RetrievalService(session, comp)
            results, _debug = await svc.search(
                query,
                collection_name=collection,
                top_k=top_k,
                filters=filters,
                enable_graph=enable_graph,
            )
        if not results:
            return f'No results found for: "{query}"'

        lines = [f'Found {len(results)} results for: "{query}"\n']
        for i, r in enumerate(results, 1):
            source = r.source_type
            doc_name = r.metadata.get("source_name") or r.document_id
            lines.append(
                f"[{i}] Score: {r.score:.4f} | Source: {source} | "
                f"Document: {doc_name}\n{r.text}\n"
            )
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.exception("rag_search_failed", error=str(e))
        return f"Search error: {type(e).__name__}: {e}"


async def _rag_ingest_url(
    url: str,
    collection: str = "default",
    tags: list[str] | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
    enable_graph: bool = False,
) -> str:
    try:
        from rag_service.services.collection_service import CollectionService
        from rag_service.services.ingest_service import IngestService

        async with _session() as (session, comp):
            cs = CollectionService(session, comp)
            existing = await cs.get_collection(collection)
            if existing is None:
                await cs.create_collection(collection)
            svc = IngestService(session, comp)
            result = await svc.ingest_url(
                url,
                collection,
                tags=tags,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                chunker=None,
                enable_graph=enable_graph,
                force=True,
            )
        return (
            f"Ingested: {url}\n"
            f"  Document ID: {result['document_id']}\n"
            f"  Chunks created: {result['chunk_count']}\n"
            f"  Collection: {result['collection']}\n"
            f"  Status: {result['status']}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("rag_ingest_url_failed", error=str(e))
        return f"Ingest error: {type(e).__name__}: {e}"


async def _rag_ingest_text(
    text: str,
    title: str = "text-ingest",
    collection: str = "default",
    tags: list[str] | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
    enable_graph: bool = False,
) -> str:
    try:
        from rag_service.services.collection_service import CollectionService
        from rag_service.services.ingest_service import IngestService

        async with _session() as (session, comp):
            cs = CollectionService(session, comp)
            existing = await cs.get_collection(collection)
            if existing is None:
                await cs.create_collection(collection)
            svc = IngestService(session, comp)
            result = await svc.ingest_text(
                text,
                title,
                collection,
                tags=tags,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                chunker=None,
                enable_graph=enable_graph,
                force=True,
            )
        return (
            f"Ingested: {title}\n"
            f"  Document ID: {result['document_id']}\n"
            f"  Chunks created: {result['chunk_count']}\n"
            f"  Collection: {result['collection']}\n"
            f"  Status: {result['status']}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("rag_ingest_text_failed", error=str(e))
        return f"Ingest error: {type(e).__name__}: {e}"


async def _rag_list_collections() -> str:
    try:
        from rag_service.services.collection_service import CollectionService

        async with _session() as (session, comp):
            cols = await CollectionService(session, comp).list_collections()
        if not cols:
            return "No collections found."

        lines = [f"Collections ({len(cols)}):\n"]
        for c in cols:
            created = c.get("created_at")
            updated = c.get("updated_at")
            lines.append(f"\n  {c['name']}")
            lines.append(
                f"    Documents: {c.get('document_count', 0)}  |  "
                f"Chunks: {c.get('chunk_count', 0)}  |  Created: {created}"
            )
            lines.append(f"    Last updated: {updated}")
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        logger.exception("rag_list_collections_failed", error=str(e))
        return f"Error: {type(e).__name__}: {e}"


async def _rag_delete_document(
    document_id: str,
    collection: str = "default",
) -> str:
    try:
        from rag_service.repositories.document_repo import DocumentRepo
        from rag_service.services.collection_service import CollectionService
        from rag_service.services.document_service import DocumentService

        async with _session() as (session, comp):
            repo = DocumentRepo(session)
            doc = await repo.get(document_id)
            if doc is None:
                return f"Error: Document {document_id!r} not found"
            chunk_count = len(await repo.get_chunks(document_id))
            col_name = await CollectionService(session, comp).resolve_name(
                doc.collection_id
            )
            await DocumentService(session, comp).delete_document(document_id)
        return (
            f"Deleted document {document_id}\n"
            f"  Chunks removed: {chunk_count}\n"
            f"  Collection: {col_name}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("rag_delete_document_failed", error=str(e))
        return f"Error: {type(e).__name__}: {e}"


# --------------------------------------------------------------------------- #
# Server factory
# --------------------------------------------------------------------------- #
def create_mcp_server() -> Any:
    """Build and return the MCP server object exposing the 5 RAG tools."""
    if _HAS_FASTMCP:
        return _create_fastmcp_server()
    return _create_low_level_server()


def _create_fastmcp_server() -> FastMCP:
    mcp: FastMCP = FastMCP("rag-service")

    @mcp.tool()
    async def rag_search(
        query: str,
        collection: str = "default",
        top_k: int = 5,
        filters: dict | None = None,
        enable_graph: bool = False,
    ) -> str:
        return await _rag_search(query, collection, top_k, filters, enable_graph)

    @mcp.tool()
    async def rag_ingest_url(
        url: str,
        collection: str = "default",
        tags: list[str] | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        enable_graph: bool = False,
    ) -> str:
        return await _rag_ingest_url(
            url, collection, tags, chunk_size, chunk_overlap, enable_graph
        )

    @mcp.tool()
    async def rag_ingest_text(
        text: str,
        title: str = "text-ingest",
        collection: str = "default",
        tags: list[str] | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        enable_graph: bool = False,
    ) -> str:
        return await _rag_ingest_text(
            text, title, collection, tags, chunk_size, chunk_overlap, enable_graph
        )

    @mcp.tool()
    async def rag_list_collections() -> str:
        return await _rag_list_collections()

    @mcp.tool()
    async def rag_delete_document(
        document_id: str,
        collection: str = "default",
    ) -> str:
        return await _rag_delete_document(document_id, collection)

    return mcp


# --------------------------------------------------------------------------- #
# Low-level Server fallback (only used if FastMCP is unavailable)
# --------------------------------------------------------------------------- #
def _create_low_level_server() -> Any:  # pragma: no cover - fallback path
    from mcp.server import Server
    from mcp.types import Tool

    server: Server = Server("rag-service")

    _TOOLS = [
        Tool(
            name="rag_search",
            description="Hybrid BM25 + semantic search over a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "collection": {"type": "string", "default": "default"},
                    "top_k": {"type": "integer", "default": 5},
                    "filters": {"type": "object"},
                    "enable_graph": {"type": "boolean", "default": False},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="rag_ingest_url",
            description="Ingest a web URL into a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "collection": {"type": "string", "default": "default"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "chunk_size": {"type": "integer", "default": 800},
                    "chunk_overlap": {"type": "integer", "default": 150},
                    "enable_graph": {"type": "boolean", "default": False},
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="rag_ingest_text",
            description="Ingest raw text into a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "title": {"type": "string", "default": "text-ingest"},
                    "collection": {"type": "string", "default": "default"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "chunk_size": {"type": "integer", "default": 800},
                    "chunk_overlap": {"type": "integer", "default": 150},
                    "enable_graph": {"type": "boolean", "default": False},
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="rag_list_collections",
            description="List all collections.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="rag_delete_document",
            description="Delete a document and its chunks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "collection": {"type": "string", "default": "default"},
                },
                "required": ["document_id"],
            },
        ),
    ]

    _DISPATCH = {
        "rag_search": _rag_search,
        "rag_ingest_url": _rag_ingest_url,
        "rag_ingest_text": _rag_ingest_text,
        "rag_list_collections": _rag_list_collections,
        "rag_delete_document": _rag_delete_document,
    }

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return _TOOLS

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[Any]:
        handler = _DISPATCH.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        result = await handler(**(arguments or {}))
        from mcp.types import TextContent

        return [TextContent(type="text", text=result)]

    return server
