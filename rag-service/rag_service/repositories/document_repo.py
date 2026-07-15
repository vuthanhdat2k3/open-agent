"""Document repository — pure SQLAlchemy async access, no business logic."""

from __future__ import annotations

from sqlalchemy import delete, func, select

from rag_service.models import Chunk, Document
from rag_service.repositories.base import BaseRepo


class DocumentRepo(BaseRepo):
    async def get(self, id: str) -> Document | None:  # noqa: A002
        result = await self.session.execute(
            select(Document).where(Document.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_hash(
        self, collection_id: str, content_hash: str
    ) -> Document | None:
        # ``limit(1)`` keeps this safe when a forced re-ingest has produced
        # more than one document sharing the same content hash.
        result = await self.session.execute(
            select(Document)
            .where(
                Document.collection_id == collection_id,
                Document.content_hash == content_hash,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        collection_id: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[int, list[Document]]:
        conditions = []
        if collection_id is not None:
            conditions.append(Document.collection_id == collection_id)
        if status is not None:
            conditions.append(Document.status == status)
        if source_type is not None:
            conditions.append(Document.source_type == source_type)

        count_stmt = select(func.count()).select_from(Document)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total = await self.session.execute(count_stmt)
        total_count = int(total.scalar() or 0)

        page_stmt = select(Document).order_by(Document.created_at.desc())
        if conditions:
            page_stmt = page_stmt.where(*conditions)
        page_stmt = page_stmt.limit(limit).offset(offset)
        result = await self.session.execute(page_stmt)
        return total_count, list(result.scalars().all())

    async def create(self, **fields: object) -> Document:
        tags = fields.pop("tags", None)
        doc_metadata = fields.pop("doc_metadata", None)

        document = Document(**fields)  # type: ignore[arg-type]
        if tags is not None:
            document.tags = tags  # type: ignore[assignment]
        if doc_metadata is not None:
            document.doc_metadata = doc_metadata  # type: ignore[assignment]

        self.session.add(document)
        await self.session.flush()
        return document

    async def update(self, doc: Document, **fields: object) -> None:
        tags = fields.pop("tags", None)
        doc_metadata = fields.pop("doc_metadata", None)

        for key, value in fields.items():
            setattr(doc, key, value)
        if tags is not None:
            doc.tags = tags  # type: ignore[assignment]
        if doc_metadata is not None:
            doc.doc_metadata = doc_metadata  # type: ignore[assignment]

        await self.session.flush()

    async def delete(self, doc: Document) -> None:
        await self.session.delete(doc)

    async def get_chunks(self, document_id: str) -> list[Chunk]:
        result = await self.session.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())

    async def delete_chunks(self, document_id: str) -> None:
        await self.session.execute(
            delete(Chunk).where(Chunk.document_id == document_id)
        )
        await self.session.flush()
