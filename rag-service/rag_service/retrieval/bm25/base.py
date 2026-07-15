"""BM25 index abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BM25Index(ABC):
    @abstractmethod
    async def add(self, collection_id: str, chunks: list) -> None:
        """Add chunks to the index (rebuilds the model)."""

    @abstractmethod
    async def remove(self, collection_id: str, chunk_ids: list[str]) -> None:
        """Remove chunks by id (rebuilds the model)."""

    @abstractmethod
    async def search(
        self, collection_id: str, query: str, top_k: int = 50
    ) -> list[tuple[str, float]]:
        """Return ``[(chunk_id, score)]`` sorted descending."""

    @abstractmethod
    async def save(self, collection_id: str) -> None:
        """Persist index state."""

    @abstractmethod
    async def load(self, collection_id: str) -> None:
        """Load persisted index state."""

    @abstractmethod
    async def delete_collection(self, collection_id: str) -> None:
        """Drop a collection's index."""
