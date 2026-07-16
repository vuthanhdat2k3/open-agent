"""Qdrant vector store backend (async client, batched ingest).

Implements :class:`rag_service.retrieval.vector.base.VectorStore` on top of
``qdrant-client``'s AsyncQdrantClient. Points are upserted in batches with the
chunk text + metadata carried as payloads, so :meth:`get_by_ids` can reconstruct
:class:`TextChunk` objects directly (matching the in-memory store's contract and
keeping retrieval independent of the SQL chunk store).

Collection naming: Qdrant collection names must match ``^[a-zA-Z_][a-zA-Z0-9_]*$``
and be <= 255 chars. We sanitize the logical collection name into a stable,
collision-resistant Qdrant collection name.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models

# Qdrant point IDs must be unsigned ints or UUIDs. Map logical string chunk_ids
# (e.g. "chunk_abc123") to a deterministic UUID via UUID5 so the same chunk_id
# always resolves to the same point id across upsert/delete/get_by_ids.
_POINT_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_POINT_NS, chunk_id))

from rag_service.exceptions import VectorStoreUnavailableError
from rag_service.pipeline.base import TextChunk
from rag_service.retrieval.vector.base import VectorStore

# Qdrant collection-name rule: start with letter/underscore, then [letter/digit/_].
_QDRANT_NAME_RE = re.compile(r"[^a-zA-Z0-9_]")
_MAX_QDRANT_NAME = 255


def _sanitize_collection(name: str) -> str:
    """Map a logical collection name to a valid Qdrant collection name.

    Falls back to a hash suffix when the sanitized form is empty or too long,
    preserving uniqueness across collections that collapse to the same prefix.
    """
    cleaned = _QDRANT_NAME_RE.sub("_", name)
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = "_" + cleaned
    if len(cleaned) > _MAX_QDRANT_NAME:
        # Keep a prefix and a stable hash of the full name to avoid collisions.
        import hashlib

        suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]
        cleaned = cleaned[: _MAX_QDRANT_NAME - len(suffix) - 1] + "_" + suffix
    return cleaned


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    import math

    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    denom = na * nb
    return dot / denom if denom else 0.0


class QdrantStore(VectorStore):
    """Async Qdrant-backed vector store with batched ingest.

    Throughput notes:
    - Upserts are chunked into ``upsert_batch_size`` points and awaited
      concurrently (bounded by ``upsert_concurrency``) to saturate the server
      without exploding memory.
    - ``on_disk`` offloads vectors to disk (mmap) for large collections while
      keeping recall.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        on_disk: bool | None = None,
        distance: str = "Cosine",
        upsert_batch_size: int = 256,
        upsert_concurrency: int = 8,
    ) -> None:
        from rag_service.config import settings

        self._url = url or settings.qdrant_url
        self._api_key = api_key if api_key is not None else settings.qdrant_api_key
        self._timeout = timeout if timeout is not None else settings.qdrant_timeout
        self._on_disk = on_disk if on_disk is not None else settings.qdrant_on_disk
        self._distance = distance
        self._upsert_batch_size = max(1, upsert_batch_size)
        self._upsert_concurrency = max(1, upsert_concurrency)
        self._lock = asyncio.Lock()
        # Cache resolved Qdrant collection names so we don't re-hash every call.
        self._name_cache: dict[str, str] = {}
        self._client: AsyncQdrantClient | None = None

    # ------------------------------------------------------------------ #
    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            try:
                self._client = AsyncQdrantClient(
                    url=self._url,
                    api_key=self._api_key or None,
                    timeout=self._timeout,
                )
            except Exception as exc:  # noqa: BLE001
                raise VectorStoreUnavailableError(
                    f"Qdrant client init failed: {exc}"
                ) from exc
        return self._client

    def _qname(self, collection: str) -> str:
        cached = self._name_cache.get(collection)
        if cached is None:
            cached = _sanitize_collection(collection)
            self._name_cache[collection] = cached
        return cached

    # ------------------------------------------------------------------ #
    async def ensure_collection(self, name: str, dimensions: int) -> None:
        qname = self._qname(name)
        try:
            exists = await self.client.collection_exists(qname)
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreUnavailableError(
                f"Qdrant unreachable: {exc}"
            ) from exc
        if exists:
            return
        try:
            await self.client.create_collection(
                collection_name=qname,
                vectors_config=models.VectorParams(
                    size=dimensions,
                    distance=getattr(models.Distance, self._distance, models.Distance.COSINE),
                    on_disk=self._on_disk or None,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreUnavailableError(
                f"Qdrant create_collection failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    def _to_point(self, chunk: TextChunk, vector: list[float]) -> models.PointStruct:
        return models.PointStruct(
            id=_point_id(chunk.chunk_id),
            vector=vector,
            payload={
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "metadata": chunk.metadata,
            },
        )

    @staticmethod
    def _point_to_chunk(point: Any) -> TextChunk:
        p = point.payload or {}
        md = p.get("metadata") or {}
        return TextChunk(
            text=p.get("text", ""),
            chunk_id=p.get("chunk_id", str(point.id)),
            start_char=int(p.get("start_char", 0) or 0),
            end_char=int(p.get("end_char", 0) or 0),
            chunk_index=int(p.get("chunk_index", 0) or 0),
            metadata=md,
        )

    # ------------------------------------------------------------------ #
    async def upsert(
        self,
        collection: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreUnavailableError("chunk/vector count mismatch")
        if not chunks:
            return

        qname = self._qname(collection)
        # (Re)ensure the collection exists with the right dimensions.
        if vectors:
            await self.ensure_collection(collection, len(vectors[0]))

        points = [self._to_point(c, v) for c, v in zip(chunks, vectors)]

        # Split into batches and upsert concurrently with bounded parallelism.
        sem = asyncio.Semaphore(self._upsert_concurrency)

        async def _upsert_batch(batch: list[models.PointStruct]) -> None:
            async with sem:
                try:
                    await self.client.upsert(
                        collection_name=qname, points=batch, wait=True
                    )
                except Exception as exc:  # noqa: BLE001
                    raise VectorStoreUnavailableError(
                        f"Qdrant upsert failed: {exc}"
                    ) from exc

        batches = [
            points[i : i + self._upsert_batch_size]
            for i in range(0, len(points), self._upsert_batch_size)
        ]
        await asyncio.gather(*(_upsert_batch(b) for b in batches))

    # ------------------------------------------------------------------ #
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[tuple[str, float]]:
        qname = self._qname(collection)
        qfilter = self._build_filter(filters) if filters else None
        try:
            hits = await self.client.query_points(
                collection_name=qname,
                query=query_vector,
                limit=top_k,
                query_filter=qfilter,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:  # noqa: BLE001
            # Empty/unknown collection -> no results (mirrors MemoryVectorStore).
            if "not found" in str(exc).lower():
                return []
            raise VectorStoreUnavailableError(
                f"Qdrant search failed: {exc}"
            ) from exc
        # ``query_points`` already returns a similarity-style score for COSINE /
        # DOT (1.0 == identical) and a distance for EUCLIDEAN (lower == closer).
        # Normalize everything to similarity so callers see scores aligned with
        # the in-memory store (higher == more relevant).
        results: list[tuple[str, float]] = []
        for h in hits.points:
            score = float(h.score)
            if self._distance.upper() == "EUCLID":
                score = 1.0 / (1.0 + score)
            cid = (h.payload or {}).get("chunk_id", str(h.id))
            results.append((str(cid), score))
        return results

    # ------------------------------------------------------------------ #
    async def get_by_ids(
        self, collection: str, chunk_ids: list[str]
    ) -> list[TextChunk]:
        if not chunk_ids:
            return []
        qname = self._qname(collection)
        try:
            points = await self.client.retrieve(
                collection_name=qname,
                ids=[_point_id(c) for c in chunk_ids],
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:  # noqa: BLE001
            if "not found" in str(exc).lower():
                return []
            raise VectorStoreUnavailableError(
                f"Qdrant get_by_ids failed: {exc}"
            ) from exc
        # Preserve the requested order.
        by_id = {(p.payload or {}).get("chunk_id", str(p.id)): p for p in points}
        out: list[TextChunk] = []
        for cid in chunk_ids:
            p = by_id.get(cid)
            if p is not None:
                out.append(self._point_to_chunk(p))
        return out

    # ------------------------------------------------------------------ #
    async def delete(self, collection: str, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        qname = self._qname(collection)
        try:
            await self.client.delete(
                collection_name=qname,
                points_selector=models.PointIdsList(
                    points=[_point_id(c) for c in chunk_ids]
                ),
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            if "not found" in str(exc).lower():
                return
            raise VectorStoreUnavailableError(
                f"Qdrant delete failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    async def delete_collection(self, collection: str) -> None:
        qname = self._qname(collection)
        try:
            await self.client.delete_collection(qname)
        except Exception as exc:  # noqa: BLE001
            if "not found" in str(exc).lower():
                return
            raise VectorStoreUnavailableError(
                f"Qdrant delete_collection failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_filter(filters: dict) -> models.Filter:
        must: list[models.FieldCondition] = []
        if filters.get("document_id"):
            must.append(
                models.FieldCondition(
                    key="metadata.document_id",
                    match=models.MatchValue(value=filters["document_id"]),
                )
            )
        if filters.get("source_type"):
            must.append(
                models.FieldCondition(
                    key="metadata.source_type",
                    match=models.MatchValue(value=filters["source_type"]),
                )
            )
        if filters.get("tags"):
            wanted = set(filters["tags"])
            # tags stored as a list -> match any
            must.append(
                models.FieldCondition(
                    key="metadata.tags",
                    match=models.MatchAny(any=list(wanted)),
                )
            )
        return models.Filter(must=must)
