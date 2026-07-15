"""Retrieval service — hybrid search over a collection."""

from __future__ import annotations

from rag_service.schemas.retrieval import RetrievalResult


class RetrievalService:
    def __init__(self, session: object, comp: object) -> None:
        self.session = session
        self.comp = comp

    async def search(
        self,
        query: str,
        collection_name: str = "default",
        top_k: int = 5,
        candidate_k: int = 50,
        filters: dict | None = None,
        enable_graph: bool = False,
        debug: bool = False,
    ) -> tuple[list[RetrievalResult], dict | None]:
        return await self.comp.retriever.search(
            query=query,
            collection_id=collection_name,
            top_k=top_k,
            candidate_k=candidate_k,
            filters=filters,
            enable_graph=enable_graph,
            debug=debug,
        )
