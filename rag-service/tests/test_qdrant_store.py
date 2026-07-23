"""Unit tests for the Qdrant vector store backend.

These exercise :class:`rag_service.retrieval.vector.qdrant.QdrantStore` against
an in-memory Qdrant instance (``location=":memory:"``), so no external service
is required. They cover the contract the rest of the service depends on:

- upsert writes points and persists (within the in-memory instance)
- search returns logical chunk_ids ranked by cosine similarity (highest first)
- get_by_ids returns chunks in the requested order with correct text/metadata
- delete removes points
- filters (document_id / source_type / tags) narrow results
- batch ingest of many chunks succeeds in one call
- logical chunk_id strings are mapped to stable Qdrant UUIDs
"""

from __future__ import annotations

import asyncio

from qdrant_client import AsyncQdrantClient

from rag_service.pipeline.base import TextChunk
from rag_service.retrieval.vector.qdrant import QdrantStore, _point_id


def _make_store() -> QdrantStore:
    """Build a QdrantStore backed by an in-memory Qdrant client.

    The store's lazy client is replaced with a ``:memory:`` instance so the
    test needs no running Qdrant server.
    """
    store = QdrantStore.__new__(QdrantStore)
    store._url = ":memory:"
    store._api_key = ""
    store._timeout = 30
    store._on_disk = False
    store._distance = "Cosine"
    store._upsert_batch_size = 256
    store._upsert_concurrency = 8
    store._lock = asyncio.Lock()
    store._name_cache = {}
    store._client = AsyncQdrantClient(location=":memory:", timeout=30)
    return store


def _chunks() -> list[TextChunk]:
    return [
        TextChunk(
            text="The cat sat on the mat",
            chunk_id="c1",
            metadata={"document_id": "d1", "source_type": "text", "tags": ["a"]},
        ),
        TextChunk(
            text="Dogs run in the park",
            chunk_id="c2",
            metadata={"document_id": "d1", "source_type": "text", "tags": ["b"]},
        ),
        TextChunk(
            text="Machine learning models embed text",
            chunk_id="c3",
            metadata={"document_id": "d2", "source_type": "text", "tags": ["ml"]},
        ),
    ]


def _vectors() -> list[list[float]]:
    return [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]


async def test_upsert_and_search_ranking():
    store = _make_store()
    await store.upsert("col", _chunks(), _vectors())
    res = await store.search("col", [1.0, 0, 0], top_k=3)
    assert res[0][0] == "c1"
    assert abs(res[0][1] - 1.0) < 1e-6  # identical vector -> similarity 1.0
    # c2/c3 are orthogonal to the query -> similarity ~0
    assert all(abs(s) < 1e-6 for _, s in res[1:])


async def test_get_by_ids_preserves_order_and_payload():
    store = _make_store()
    await store.upsert("col", _chunks(), _vectors())
    got = await store.get_by_ids("col", ["c2", "c1"])
    assert [c.chunk_id for c in got] == ["c2", "c1"]
    assert got[0].text == "Dogs run in the park"
    assert got[1].metadata["document_id"] == "d1"


async def test_delete_removes_point():
    store = _make_store()
    await store.upsert("col", _chunks(), _vectors())
    await store.delete("col", ["c1"])
    res = await store.search("col", [1.0, 0, 0], top_k=3)
    assert all(cid != "c1" for cid, _ in res)


async def test_filter_by_tags():
    store = _make_store()
    await store.upsert("col", _chunks(), _vectors())
    fr = await store.search("col", [0, 1.0, 0], top_k=3, filters={"tags": ["ml"]})
    assert fr and fr[0][0] == "c3"


async def test_filter_by_document_id():
    store = _make_store()
    await store.upsert("col", _chunks(), _vectors())
    fr = await store.search("col", [0, 1.0, 0], top_k=3, filters={"document_id": "d1"})
    assert {cid for cid, _ in fr} == {"c1", "c2"}


async def test_batch_upsert_large():
    store = _make_store()
    n = 600
    chunks = [
        TextChunk(text=f"t{i}", chunk_id=f"k{i}", metadata={"document_id": "d3"})
        for i in range(n)
    ]
    vectors = [[float(i == j) for j in range(3)] for i in range(n)]
    await store.upsert("big", chunks, vectors)

    cnt = await store.client.count(store._qname("big"))
    assert cnt.count == n


async def test_point_id_is_stable_uuid():
    # Same logical id -> same UUID (needed for upsert/delete/get_by_ids consistency)
    a = _point_id("chunk_abc123")
    b = _point_id("chunk_abc123")
    assert a == b
    # Different ids -> different UUIDs
    assert _point_id("chunk_xyz") != a
    # Valid UUID format
    import uuid

    uuid.UUID(a)


async def test_search_empty_collection_returns_empty():
    store = _make_store()
    res = await store.search("missing", [1.0, 0, 0], top_k=3)
    assert res == []
