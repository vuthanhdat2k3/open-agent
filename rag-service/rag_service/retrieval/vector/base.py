"""Vector store abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rag_service.pipeline.base import TextChunk


class VectorStore(ABC):
    @abstractmethod
    async def ensure_collection(self, name: str, dimensions: int) -> None:
        """Create the collection if it does not exist."""

    @abstractmethod
    async def upsert(
        self,
        collection: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None:
        """Store chunk vectors + payloads."""

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 50,
        filters: dict | None = None,
    ) -> list[tuple[str, float]]:
        """Return ``[(chunk_id, score)]`` sorted descending."""

    @abstractmethod
    async def delete(self, collection: str, chunk_ids: list[str]) -> None:
        """Remove specific chunk points."""

    @abstractmethod
    async def delete_collection(self, collection: str) -> None:
        """Drop an entire collection."""

    @abstractmethod
    async def get_by_ids(
        self, collection: str, chunk_ids: list[str]
    ) -> list[TextChunk]:
        """Fetch full chunk content + metadata by id."""
