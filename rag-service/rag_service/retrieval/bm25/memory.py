"""In-memory BM25 index (rank_bm25), with pickle persistence.

Default ``memory`` backend. No external service required. Persisted per
collection under ``RAG_BM25_PERSIST_DIR`` and reloaded on startup.
"""

from __future__ import annotations

import pickle
from typing import Any

from rank_bm25 import BM25Okapi

from rag_service.config import settings
from rag_service.pipeline.base import TextChunk
from rag_service.retrieval.bm25.base import BM25Index
from rag_service.core.logging import logger


class InMemoryBM25(BM25Index):
    """Holds a BM25Okapi model per collection, persisted to disk as pickle."""

    def __init__(self, k1: float | None = None, b: float | None = None, epsilon: float | None = None) -> None:
        self.k1 = settings.bm25_k1 if k1 is None else k1
        self.b = settings.bm25_b if b is None else b
        self.epsilon = settings.bm25_epsilon if epsilon is None else epsilon
        self._indexes: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    def _tokenize(self, text: str) -> list[str]:
        return text.lower().split()

    def _build(self, corpus: list[list[str]]) -> BM25Okapi:
        return BM25Okapi(corpus, k1=self.k1, b=self.b, epsilon=self.epsilon)

    # ------------------------------------------------------------------ #
    async def add(self, collection_id: str, chunks: list[TextChunk]) -> None:
        entry = self._indexes.setdefault(collection_id, {"chunk_ids": [], "corpus": []})
        for c in chunks:
            entry["chunk_ids"].append(c.chunk_id)
            entry["corpus"].append(self._tokenize(c.text))
        entry["model"] = self._build(entry["corpus"])
        await self.save(collection_id)

    async def remove(self, collection_id: str, chunk_ids: list[str]) -> None:
        entry = self._indexes.get(collection_id)
        if not entry:
            return
        wanted = set(chunk_ids)
        idx_keep = [i for i, cid in enumerate(entry["chunk_ids"]) if cid not in wanted]
        entry["chunk_ids"] = [entry["chunk_ids"][i] for i in idx_keep]
        entry["corpus"] = [entry["corpus"][i] for i in idx_keep]
        if entry["chunk_ids"]:
            entry["model"] = self._build(entry["corpus"])
        else:
            entry.pop("model", None)

    async def search(self, collection_id: str, query: str, top_k: int = 50):
        entry = self._indexes.get(collection_id)
        if not entry or "model" not in entry:
            return []
        tokens = self._tokenize(query)
        scores = entry["model"].get_scores(tokens)
        ranked = sorted(
            zip(entry["chunk_ids"], scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:top_k]

    async def save(self, collection_id: str) -> None:
        entry = self._indexes.get(collection_id)
        if not entry:
            return
        try:
            settings.bm25_persist_dir.mkdir(parents=True, exist_ok=True)
            path = settings.bm25_persist_dir / f"{collection_id}.pkl"
            with open(path, "wb") as f:
                # Persist corpus + ids (rebuild model on load)
                pickle.dump(
                    {"chunk_ids": entry["chunk_ids"], "corpus": entry["corpus"]},
                    f,
                )
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("bm25_save_failed", collection=collection_id, error=str(exc))

    async def load(self, collection_id: str) -> None:
        path = settings.bm25_persist_dir / f"{collection_id}.pkl"
        if not path.exists():
            return
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            entry = self._indexes.setdefault(
                collection_id,
                {"chunk_ids": data.get("chunk_ids", []), "corpus": data.get("corpus", [])},
            )
            entry["chunk_ids"] = data.get("chunk_ids", [])
            entry["corpus"] = data.get("corpus", [])
            if entry["chunk_ids"]:
                entry["model"] = self._build(entry["corpus"])
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("bm25_load_failed", collection=collection_id, error=str(exc))

    async def delete_collection(self, collection_id: str) -> None:
        self._indexes.pop(collection_id, None)
        try:
            path = settings.bm25_persist_dir / f"{collection_id}.pkl"
            if path.exists():
                path.unlink()
        except Exception:  # pragma: no cover
            pass
