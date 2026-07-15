"""Collection repository — pure SQLAlchemy async access, no business logic."""

from __future__ import annotations

from sqlalchemy import func, select

from rag_service.models import Collection, Chunk, Document
from rag_service.repositories.base import BaseRepo


class CollectionRepo(BaseRepo):
    async def get_by_name(self, name: str) -> Collection | None:
        result = await self.session.execute(
            select(Collection).where(Collection.name == name)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, id: str) -> Collection | None:  # noqa: A002
        result = await self.session.execute(
            select(Collection).where(Collection.id == id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Collection]:
        result = await self.session.execute(
            select(Collection).order_by(Collection.created_at)
        )
        return list(result.scalars().all())

    async def create(
        self,
        name: str,
        description: str | None = None,
        embedding_model: str = "text-embedding-3-small",
        embedding_dimensions: int = 1536,
    ) -> Collection:
        collection = Collection(
            name=name,
            description=description,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        )
        self.session.add(collection)
        await self.session.flush()
        return collection

    async def delete(self, collection: Collection) -> None:
        await self.session.delete(collection)

    async def count_documents(self, id: str) -> int:  # noqa: A002
        result = await self.session.execute(
            select(func.count(Document.id)).where(Document.collection_id == id)
        )
        return int(result.scalar() or 0)

    async def count_chunks(self, id: str) -> int:  # noqa: A002
        result = await self.session.execute(
            select(func.count(Chunk.id)).where(Chunk.collection_id == id)
        )
        return int(result.scalar() or 0)
