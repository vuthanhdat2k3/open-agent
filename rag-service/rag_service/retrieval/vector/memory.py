"""Zero-dependency in-memory vector store (numpy cosine similarity).

This is the **default-safe** backend: it requires no external service, so the
RAG service boots and serves real retrieval traffic out of the box. Switch to
Qdrant/Chroma by setting ``RAG_VECTOR_STORE``.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import numpy as np

from rag_service.exceptions import VectorStoreUnavailableError
from rag_service.pipeline.base import TextChunk
from rag_service.retrieval.vector.base import VectorStore


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class MemoryVectorStore(VectorStore):
    """Thread-safe in-process vector store backed by numpy."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # collection -> {"ids": [...], "vecs": np.ndarray, "chunks": {id: TextChunk}}
        self._data: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    async def ensure_collection(self, name: str, dimensions: int) -> None:
        with self._lock:
            if name not in self._data:
                self._data[name] = {
                    "ids": [],
                    "vecs": np.empty((0, dimensions), dtype=np.float32),
                    "chunks": {},
                }

    async def upsert(
        self,
        collection: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreUnavailableError("chunk/vector count mismatch")
        dims = len(vectors[0]) if vectors else 0
        with self._lock:
            store = self._data.setdefault(
                collection,
                {
                    "ids": [],
                    "vecs": np.empty((0, dims), dtype=np.float32),
                    "chunks": {},
                },
            )
            for chunk, vec in zip(chunks, vectors):
                cid = chunk.chunk_id
                if cid in store["chunks"]:
                    # replace in-place
                    idx = store["ids"].index(cid)
                    store["vecs"][idx] = np.asarray(vec, dtype=np.float32)
                    store["chunks"][cid] = chunk
                else:
                    store["ids"].append(cid)
                    store["vecs"] = np.vstack(
                        [store["vecs"], np.asarray(vec, dtype=np.float32)]
                    )
                    store["chunks"][cid] = chunk

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[tuple[str, float]]:
        with self._lock:
            store = self._data.get(collection)
            if not store or not store["ids"]:
                return []
            q = np.asarray(query_vector, dtype=np.float32)
            # cosine over all
            norms = np.linalg.norm(store["vecs"], axis=1)
            denom = norms * np.linalg.norm(q)
            sims = np.zeros(len(store["ids"]), dtype=np.float32)
            nonzero = denom > 0
            sims[nonzero] = (store["vecs"] @ q)[nonzero] / denom[nonzero]
            results = []
            for cid, sim, idx in zip(store["ids"], sims, range(len(store["ids"]))):
                chunk = store["chunks"][cid]
                if filters and not _matches_filters(chunk, filters):
                    continue
                results.append((cid, float(sim)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def delete(self, collection: str, chunk_ids: list[str]) -> None:
        with self._lock:
            store = self._data.get(collection)
            if not store:
                return
            keep_idx = [i for i, cid in enumerate(store["ids"]) if cid not in set(chunk_ids)]
            store["ids"] = [store["ids"][i] for i in keep_idx]
            store["vecs"] = store["vecs"][keep_idx] if keep_idx else np.empty(
                (0, store["vecs"].shape[1]), dtype=np.float32
            )
            for cid in chunk_ids:
                store["chunks"].pop(cid, None)

    async def delete_collection(self, collection: str) -> None:
        with self._lock:
            self._data.pop(collection, None)

    async def get_by_ids(
        self, collection: str, chunk_ids: list[str]
    ) -> list[TextChunk]:
        with self._lock:
            store = self._data.get(collection, {})
            wanted = set(chunk_ids)
            return [store["chunks"][cid] for cid in chunk_ids if cid in store["chunks"]]

    # convenience used by tests / tooling
    async def count(self, collection: str) -> int:
        with self._lock:
            return len(self._data.get(collection, {}).get("ids", []))


def _matches_filters(chunk: TextChunk, filters: dict) -> bool:
    md = chunk.metadata
    if filters.get("document_id") and md.get("document_id") != filters["document_id"]:
        return False
    if filters.get("source_type") and md.get("source_type") != filters["source_type"]:
        return False
    if filters.get("tags"):
        chunk_tags = set(md.get("tags", []))
        if not chunk_tags.intersection(set(filters["tags"])):
            return False
    return True
