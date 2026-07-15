"""Graph retriever — LightRAG-style local + global search over extracted graph.

This module is imported lazily by :func:`rag_service.core.factory.build_graph_retriever`
only when ``settings.enable_graph`` is True, so the service boots cleanly without
``networkx`` / ``openai`` installed.  All public methods are exception-safe and
return ``[]`` / empty results when the graph is empty or unavailable.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from rag_service.core.logging import logger
from rag_service.pipeline.base import TextChunk
from rag_service.retrieval.graph.extractor import EntityRelationExtractor
from rag_service.retrieval.graph.store import NetworkXGraphStore


class GraphRetriever:
    """Ingest extracted graphs and search them for relevant chunk ids."""

    def __init__(self) -> None:
        self._extractor = EntityRelationExtractor()
        self._stores: dict[str, NetworkXGraphStore] = {}

    # ------------------------------------------------------------------ #
    def _store(self, collection_id: str) -> NetworkXGraphStore:
        store = self._stores.get(collection_id)
        if store is None:
            store = NetworkXGraphStore(collection_id)
            self._stores[collection_id] = store
        return store

    # ------------------------------------------------------------------ #
    async def ingest(self, chunks: list[TextChunk]) -> None:
        """Extract entities/relations for each chunk and merge into the graph."""
        by_collection: dict[str, list[TextChunk]] = defaultdict(list)
        for c in chunks:
            cid = c.metadata.get("collection_id")
            if cid:
                by_collection[cid].append(c)

        for collection_id, col_chunks in by_collection.items():
            try:
                store = self._store(collection_id)
                graph_data_list = [
                    await self._extractor.extract(c.text, c.chunk_id)
                    for c in col_chunks
                ]
                graph_data_list = [g for g in graph_data_list if not g.is_empty()]
                if not graph_data_list:
                    continue
                await store.upsert(collection_id, graph_data_list)
                await store.save(collection_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "graph_ingest_failed", collection=collection_id, error=str(exc)
                )

    # ------------------------------------------------------------------ #
    async def search(
        self,
        query: str,
        collection_id: str,
        top_k: int = 20,
        mode: str = "hybrid",
    ) -> list[tuple[str, float]]:
        """Return ``[(chunk_id, score)]`` for a query, or ``[]`` if unavailable."""
        try:
            store = self._stores.get(collection_id)
            if store is None:
                store = self._store(collection_id)
                try:
                    await store.load(collection_id)
                except Exception:  # noqa: BLE001
                    pass
            if store is None or store.graph.number_of_nodes() == 0:
                return []

            g = store.graph

            # Extract query entities (reuse the same extractor on the query).
            q_graph = await self._extractor.extract(query, "query")
            query_entities = {
                (e.get("id") or e.get("name")) for e in q_graph.entities
            }

            chunk_scores: dict[str, float] = defaultdict(float)

            # Local search: chunks attached to matched entities.
            for ent in query_entities:
                if g.has_node(ent):
                    for cid in g.nodes[ent].get("chunk_ids", []):
                        chunk_scores[cid] += 1.0

            # Optional global expansion (BFS, depth 2).
            if mode in ("hybrid", "global"):
                frontier = set(query_entities)
                for _ in range(2):
                    nxt: set[str] = set()
                    for node in frontier:
                        if not g.has_node(node):
                            continue
                        for nb in g.successors(node):
                            nxt.add(nb)
                            for cid in g.nodes[nb].get("chunk_ids", []):
                                chunk_scores[cid] += 0.5
                        for nb in g.predecessors(node):
                            nxt.add(nb)
                            for cid in g.nodes[nb].get("chunk_ids", []):
                                chunk_scores[cid] += 0.5
                    frontier = nxt

            if not chunk_scores:
                return []
            ranked = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)
            return ranked[:top_k]
        except Exception as exc:  # noqa: BLE001 - never raise
            logger.warning("graph_search_failed", collection=collection_id, error=str(exc))
            return []
