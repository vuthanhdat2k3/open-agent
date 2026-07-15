"""Document service — document + job inspection and deletion."""

from __future__ import annotations

from rag_service.core.logging import logger
from rag_service.exceptions import DocumentNotFoundError, JobNotFoundError
from rag_service.models import Document, IngestJob
from rag_service.repositories.chunk_repo import ChunkRepo
from rag_service.repositories.collection_repo import CollectionRepo
from rag_service.repositories.document_repo import DocumentRepo
from rag_service.repositories.job_repo import JobRepo
from rag_service.services.collection_service import CollectionService


def _document_to_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "collection_id": doc.collection_id,
        "name": doc.name,
        "source_type": doc.source_type,
        "source_url": doc.source_url,
        "content_hash": doc.content_hash,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "token_count": doc.token_count,
        "tags": doc.tags,
        "metadata": doc.doc_metadata,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


class DocumentService:
    def __init__(self, session: object, comp: object) -> None:
        self.session = session
        self.comp = comp
        self.repo = DocumentRepo(session)
        self.chunk_repo = ChunkRepo(session)
        self.job_repo = JobRepo(session)
        self.collection_service = CollectionService(session, comp)

    # ------------------------------------------------------------------ #
    async def list_documents(
        self,
        collection_id: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        total, docs = await self.repo.list(
            collection_id=collection_id,
            status=status,
            source_type=source_type,
            limit=limit,
            offset=offset,
        )
        return total, [_document_to_dict(d) for d in docs]

    async def get_document(self, document_id: str) -> dict | None:
        doc = await self.repo.get(document_id)
        if doc is None:
            return None

        chunks = await self.repo.get_chunks(document_id)
        chunk_dicts = [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "text": c.text,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "token_count": c.token_count,
            }
            for c in chunks
        ]

        result = _document_to_dict(doc)
        result["chunks"] = chunk_dicts
        return result

    async def delete_document(self, document_id: str) -> None:
        doc = await self.repo.get(document_id)
        if doc is None:
            raise DocumentNotFoundError(document_id)

        name = await self.collection_service.resolve_name(doc.collection_id)
        chunks = await self.repo.get_chunks(document_id)
        chunk_ids = [c.id for c in chunks]

        if chunk_ids:
            try:
                await self.comp.vector_store.delete(name, chunk_ids)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning(
                    "vector_store_delete_failed", document=document_id, error=str(exc)
                )
            try:
                await self.comp.bm25_index.remove(name, chunk_ids)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning(
                    "bm25_remove_failed", document=document_id, error=str(exc)
                )

        await self.repo.delete(doc)

    async def get_job(self, job_id: str) -> dict | None:
        job = await self.job_repo.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)

        return {
            "job_id": job.id,
            "document_id": job.document_id,
            "status": job.status,
            "progress": {
                "stage": job.stage,
                "chunks_processed": job.chunks_done,
                "chunks_total": job.chunks_total,
            },
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "errors": job.error_message,
        }
