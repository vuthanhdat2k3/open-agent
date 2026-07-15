"""Smoke tests for the RAG service.

These exercise the public surface (parsers, chunkers, embedders, services,
REST API, MCP server, graph layer, packaging) with zero external services,
using the in-memory fallbacks forced in ``conftest.py``.
"""

from __future__ import annotations

import os
import pathlib

import pytest


# --------------------------------------------------------------------------- #
# Pipeline: parsers / chunkers / embedders
# --------------------------------------------------------------------------- #
async def test_parser_registry_and_markdown_parse():
    from rag_service.pipeline.parser import get_parser, PARSER_REGISTRY

    assert PARSER_REGISTRY, "parser registry must be populated"
    p = get_parser("markdown")
    parsed = await p.parse(
        "# Title\n\nHello world. This is a test paragraph.\n\n## Section\nMore text here."
    )
    assert parsed.text and "Hello world" in parsed.text


async def test_chunker_registry_and_recursive_chunk():
    from rag_service.pipeline.chunker import get_chunker, CHUNKER_REGISTRY

    assert CHUNKER_REGISTRY, "chunker registry must be populated"
    c = get_chunker("recursive", 500, 50)
    chunks = c.chunk("Hello world. " * 20, {"source": "verify"})
    assert len(chunks) >= 1
    assert all(ch.text for ch in chunks)


async def test_embedder_fallback_produces_vectors():
    from rag_service.core.factory import build_embedder

    emb = build_embedder()
    vecs = await emb.embed_batch(["RAG is retrieval augmented generation", "FastAPI builds APIs"])
    assert len(vecs) == 2
    assert len(vecs[0]) > 0


# --------------------------------------------------------------------------- #
# Services: collection / ingest / hybrid retrieval
# --------------------------------------------------------------------------- #
async def test_ingest_and_hybrid_retrieval():
    from rag_service.db.base import init_db, get_sessionmaker
    from rag_service.dependencies import get_components
    from rag_service.services.collection_service import CollectionService
    from rag_service.services.ingest_service import IngestService
    from rag_service.services.retrieval_service import RetrievalService

    await init_db()
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as session:
        comp = get_components()
        cs = CollectionService(session, comp)
        if await cs.get_collection("smoke_test") is None:
            await cs.create_collection("smoke_test")
        ing = IngestService(session, comp)
        r1 = await ing.ingest_text(
            "RAG stands for Retrieval Augmented Generation.", "doc-a", "smoke_test",
            chunk_size=500, chunk_overlap=50, force=True,
        )
        r2 = await ing.ingest_text(
            "FastAPI is a web framework for building APIs.", "doc-b", "smoke_test",
            chunk_size=500, chunk_overlap=50, force=True,
        )
        await session.commit()
        assert r1["status"] == "success" and r2["status"] == "success"

        rs = RetrievalService(session, comp)
        res1, _ = await rs.search("retrieval augmented generation", collection_name="smoke_test", top_k=3)
        res2, _ = await rs.search("web framework", collection_name="smoke_test", top_k=3)
        assert res1 and res2, "hybrid retrieval must return hits for both topics"


# --------------------------------------------------------------------------- #
# REST API
# --------------------------------------------------------------------------- #
def test_rest_health_and_collections():
    from fastapi.testclient import TestClient

    from rag_service.main import create_rest_app

    client = TestClient(create_rest_app())
    h = client.get("/api/v1/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    ls = client.get("/api/v1/collections")
    assert ls.status_code == 200


# --------------------------------------------------------------------------- #
# MCP + graph + packaging
# --------------------------------------------------------------------------- #
def test_mcp_server_builds():
    from rag_service.mcp_server.server import create_mcp_server

    assert create_mcp_server() is not None


def test_graph_modules_present():
    import rag_service.retrieval.graph as G

    assert all(
        hasattr(G, n)
        for n in ("NetworkXGraphStore", "EntityRelationExtractor", "GraphRetriever")
    )


def test_packaging_files_present():
    root = pathlib.Path(__file__).resolve().parent.parent
    assert (root / "scripts" / "run.py").exists()
    assert (root / "alembic.ini").exists()
    assert (root / "alembic" / "script.py.mako").exists()

    pyproject = root / "pyproject.toml"
    assert pyproject.exists() and pyproject.stat().st_size > 0
    # Parse it (tomllib on 3.11+, tomli fallback, else just confirm readable).
    try:
        try:
            import tomllib as _toml
        except ImportError:
            import tomli as _toml  # type: ignore
        with open(pyproject, "rb") as f:
            data = _toml.load(f)
        assert "project" in data
    except ImportError:
        # Neither toml lib available on this interpreter -> file readable is enough.
        assert pyproject.read_text(encoding="utf-8")
