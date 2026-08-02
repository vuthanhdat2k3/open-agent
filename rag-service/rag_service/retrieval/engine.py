"""Hybrid retrieval engine: BM25 + semantic + RRF fusion + Cross-Encoder Reranking.

Runs the complementary signals in parallel, fuses their ranked lists with
Reciprocal Rank Fusion, applies Cross-Encoder reranking & long-context reordering,
and resolves Parent-Child relationships for full-context synthesis.
"""

from __future__ import annotations

import asyncio
import time

from rag_service.config import settings
from rag_service.pipeline.base import Embedder, TextChunk
from rag_service.retrieval.bm25.base import BM25Index
from rag_service.retrieval.reranker import CrossEncoderReranker, reorder_long_context
from rag_service.retrieval.rrf import reciprocal_rank_fusion
from rag_service.retrieval.vector.base import VectorStore
from rag_service.schemas.retrieval import RetrievalResult


class HybridRetriever:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        graph_retriever: object | None = None,
        rrf_k: int | None = None,
        bm25_weight: float | None = None,
        semantic_weight: float | None = None,
        query_cache_size: int | None = None,
        enable_reranking: bool = True,
        enable_context_reorder: bool = True,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.graph_retriever = graph_retriever
        self.rrf_k = rrf_k if rrf_k is not None else settings.rrf_k
        self.bm25_weight = bm25_weight if bm25_weight is not None else settings.rrf_bm25_weight
        self.semantic_weight = (
            semantic_weight if semantic_weight is not None else settings.rrf_semantic_weight
        )
        self.enable_reranking = enable_reranking
        self.enable_context_reorder = enable_context_reorder
        self.reranker = CrossEncoderReranker(min_score_threshold=0.15)

        self._cache: dict[str, list[float]] = {}
        self._cache_order: list[str] = []
        self._cache_max = (
            query_cache_size if query_cache_size is not None else settings.query_cache_size
        )

    # ------------------------------------------------------------------ #
    async def embed_query_cached(self, query: str) -> list[float]:
        q = query.strip()
        if q in self._cache:
            return self._cache[q]
        vec = await self.embedder.embed_query(q)
        self._cache[q] = vec
        self._cache_order.append(q)
        while len(self._cache_order) > self._cache_max:
            old = self._cache_order.pop(0)
            self._cache.pop(old, None)
        return vec

    # ------------------------------------------------------------------ #
    async def search(
        self,
        query: str,
        collection_id: str,
        top_k: int = 10,
        candidate_k: int = 50,
        filters: dict | None = None,
        enable_graph: bool = False,
        debug: bool = False,
    ) -> tuple[list[RetrievalResult], dict | None]:
        t0 = time.perf_counter()

        query_vector = await self.embed_query_cached(query)
        embed_ms = (time.perf_counter() - t0) * 1000

        bm25_t0 = time.perf_counter()
        bm25_task = self.bm25_index.search(collection_id, query, top_k=candidate_k)
        sem_task = self.vector_store.search(
            collection_id, query_vector, top_k=candidate_k, filters=filters
        )
        graph_task = (
            self.graph_retriever.search(query, collection_id, top_k=candidate_k)
            if (enable_graph and self.graph_retriever)
            else None
        )
        tasks = [bm25_task, sem_task]
        if graph_task is not None:
            tasks.append(graph_task)
        results = await asyncio.gather(*tasks)
        bm25_results, semantic_results = results[0], results[1]
        graph_results = results[2] if graph_task is not None else None

        bm25_ms = (time.perf_counter() - bm25_t0) * 1000

        ranked_lists = [bm25_results, semantic_results]
        weights = [self.bm25_weight, self.semantic_weight]
        if graph_results is not None:
            ranked_lists.append(graph_results)
            weights.append(1.0)

        sem_ms = (time.perf_counter() - bm25_t0) * 1000

        rrf_t0 = time.perf_counter()
        fused = reciprocal_rank_fusion(ranked_lists, k=self.rrf_k, weights=weights)
        rrf_ms = (time.perf_counter() - rrf_t0) * 1000

        # Fetch candidates for reranking
        candidate_ids = [cid for cid, _ in fused[:candidate_k]]
        chunks: list[TextChunk] = (
            await self.vector_store.get_by_ids(collection_id, candidate_ids) if candidate_ids else []
        )
        by_id = {c.chunk_id: c for c in chunks}

        score_map = dict(fused)
        initial_results: list[RetrievalResult] = []
        for rank, cid in enumerate(candidate_ids, start=1):
            chunk = by_id.get(cid)
            if chunk is None:
                continue
            md = chunk.metadata
            # Parent-child resolution: Use parent_text if present for synthesis
            text_content = md.get("parent_text") or chunk.text
            initial_results.append(
                RetrievalResult(
                    chunk_id=cid,
                    document_id=md.get("document_id", ""),
                    text=text_content,
                    score=round(score_map[cid], 6),
                    rank=rank,
                    source_type=md.get("source_type", "unknown"),
                    metadata=md,
                    highlights=[query.strip()],
                )
            )

        # Apply Cross-Encoder Reranking
        rerank_t0 = time.perf_counter()
        if self.enable_reranking and initial_results:
            reranked = self.reranker.rerank(query, initial_results, top_k=top_k)
        else:
            reranked = initial_results[:top_k]
        rerank_ms = (time.perf_counter() - rerank_t0) * 1000

        # Apply Long Context Reordering
        if self.enable_context_reorder:
            out = reorder_long_context(reranked)
        else:
            out = reranked

        if not debug:
            return out, None

        dbg = {
            "bm25_candidates": len(bm25_results),
            "semantic_candidates": len(semantic_results),
            "rrf_k": self.rrf_k,
            "embed_latency_ms": round(embed_ms, 2),
            "bm25_latency_ms": round(bm25_ms, 2),
            "semantic_latency_ms": round(sem_ms - bm25_ms, 2),
            "rrf_latency_ms": round(rrf_ms, 2),
            "rerank_latency_ms": round(rerank_ms, 2),
            "total_latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        return out, dbg
