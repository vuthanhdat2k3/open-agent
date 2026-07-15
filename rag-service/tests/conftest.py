"""Pytest configuration for the RAG service smoke suite.

Forces the zero-dependency backends (in-memory vector store, local hashing
embedder, in-memory BM25) so the suite runs with **no external services**.
"""

from __future__ import annotations

import os

os.environ.setdefault("RAG_ENV", "test")
os.environ.setdefault("OPENAI_API_KEY", "")

import pytest

from rag_service.config import settings

# Zero-dependency backends -> tests run offline, no Qdrant/Redis/OpenAI needed.
settings.vector_store = "memory"
settings.bm25_backend = "memory"
settings.embedder = "simple"
settings.enable_graph = False


@pytest.fixture
def components():
    from rag_service.dependencies import get_components

    return get_components()


@pytest.fixture
async def session():
    from rag_service.db.base import init_db, get_sessionmaker

    await init_db()
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as s:
        yield s
        await s.rollback()
