"""Collection service — namespace (collection) management."""

from __future__ import annotations

from rag_service.core.logging import logger
from rag_service.exceptions import AlreadyExistsError, CollectionNotFoundError
from rag_service.models import Collection
from rag_service.repositories.chunk_repo import ChunkRepo
from rag_service.repositories.collection_repo import CollectionRepo
from rag_service.repositories.document_repo import DocumentRepo


class CollectionService:
    def __init__(self, session: object, comp: object) -> None:
        self.session = session
        self.comp = comp
        self.repo = CollectionRepo(session)
        self.document_repo = DocumentRepo(session)
        self.chunk_repo = ChunkRepo(session)

    # ------------------------------------------------------------------ #
    async def list_collections(self) -> list[dict]:
        collections = await self.repo.list_all()
        out: list[dict] = []
        for c in collections:
            out.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "embedding_model": c.embedding_model,
                    "embedding_dimensions": c.embedding_dimensions,
                    "document_count": await self.repo.count_documents(c.id),
                    "chunk_count": await self.repo.count_chunks(c.id),
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                }
            )
        return out

    async def get_collection(self, name_or_id: str) -> dict | None:
        collection = await self.repo.get_by_id(name_or_id)
        if collection is None:
            collection = await self.repo.get_by_name(name_or_id)
        if collection is None:
            return None
        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "embedding_model": collection.embedding_model,
            "embedding_dimensions": collection.embedding_dimensions,
            "document_count": await self.repo.count_documents(collection.id),
            "chunk_count": await self.repo.count_chunks(collection.id),
            "created_at": collection.created_at,
            "updated_at": collection.updated_at,
        }

    async def create_collection(
        self,
        name: str,
        description: str | None = None,
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
    ) -> dict:
        existing = await self.repo.get_by_name(name)
        if existing is not None:
            raise AlreadyExistsError(f"Collection {name!r} already exists")

        collection = await self.repo.create(
            name=name,
            description=description,
            embedding_model=embedding_model or "text-embedding-3-small",
            embedding_dimensions=embedding_dimensions or 1536,
        )
        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "embedding_model": collection.embedding_model,
            "embedding_dimensions": collection.embedding_dimensions,
            "document_count": 0,
            "chunk_count": 0,
            "created_at": collection.created_at,
            "updated_at": collection.updated_at,
        }

    async def delete_collection(self, name_or_id: str) -> None:
        collection = await self.repo.get_by_id(name_or_id)
        if collection is None:
            collection = await self.repo.get_by_name(name_or_id)
        if collection is None:
            raise CollectionNotFoundError(name_or_id)

        name = collection.name
        await self.repo.delete(collection)

        try:
            await self.comp.vector_store.delete_collection(name)
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            logger.warning("vector_store_delete_collection_failed", name=name, error=str(exc))
        try:
            await self.comp.bm25_index.delete_collection(name)
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            logger.warning("bm25_delete_collection_failed", name=name, error=str(exc))

    async def ensure_default(self) -> None:
        existing = await self.repo.get_by_name("default")
        if existing is None:
            await self.repo.create(name="default")

    async def resolve_name(self, name_or_id: str) -> str:
        collection = await self.repo.get_by_id(name_or_id)
        if collection is None:
            collection = await self.repo.get_by_name(name_or_id)
        if collection is None:
            raise CollectionNotFoundError(name_or_id)
        return collection.name
