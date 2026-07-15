"""Chunk repository — pure SQLAlchemy async access, no business logic."""

from __future__ import annotations

from sqlalchemy import delete, select

from rag_service.models import Chunk
from rag_service.repositories.base import BaseRepo


class ChunkRepo(BaseRepo):
    async def add_many(self, chunks: list[Chunk]) -> None:
        self.session.add_all(chunks)
        await self.session.flush()

    async def get_by_ids(self, ids: list[str]) -> list[Chunk]:
        if not ids:
            return []
        result = await self.session.execute(
            select(Chunk).where(Chunk.id.in_(ids))
        )
        return list(result.scalars().all())

    async def delete_many(self, ids: list[str]) -> None:
        if not ids:
            return
        await self.session.execute(delete(Chunk).where(Chunk.id.in_(ids)))
        await self.session.flush()
