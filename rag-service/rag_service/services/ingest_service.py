"""Ingest service — runs the parse -> chunk -> embed -> store pipeline.

The pipeline runs synchronously (awaited) so the service works with no task
queue. Each public method performs idempotency (content-hash) checks, records
the ingest job, and delegates the heavy lifting to :meth:`_run`.
"""

from __future__ import annotations

import datetime
import hashlib
import os
from typing import Any

from rag_service.config import settings
from rag_service.core.factory import resolve_chunker, resolve_parser
from rag_service.core.logging import logger
from rag_service.exceptions import (
    CollectionNotFoundError,
    DocumentNotFoundError,
    EmptyDocumentError,
    RAGError,
    UnsupportedFormatError,
)
from rag_service.models import Chunk, Document
from rag_service.pipeline.base import IngestOptions, TextChunk
from rag_service.repositories.chunk_repo import ChunkRepo
from rag_service.repositories.collection_repo import CollectionRepo
from rag_service.repositories.document_repo import DocumentRepo
from rag_service.repositories.job_repo import JobRepo
from rag_service.services.collection_service import CollectionService

# Filename extension -> source type.
_EXT_TO_SOURCE_TYPE = {
    "pdf": "pdf",
    "docx": "docx",
    "md": "md",
    "markdown": "markdown",
    "html": "html",
    "htm": "html",
    "txt": "text",
}


class IngestService:
    def __init__(self, session: object, comp: object) -> None:
        self.session = session
        self.comp = comp
        self.collection_service = CollectionService(session, comp)
        self.collection_repo = CollectionRepo(session)
        self.document_repo = DocumentRepo(session)
        self.chunk_repo = ChunkRepo(session)
        self.job_repo = JobRepo(session)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def ingest_file(
        self,
        file_bytes: bytes,
        filename: str,
        collection_name: str,
        *,
        tags: list[str] | None = None,
        chunk_size: int,
        chunk_overlap: int,
        chunker: str | None = None,
        enable_graph: bool = False,
        force: bool = False,
    ) -> dict:
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        source_type = _EXT_TO_SOURCE_TYPE.get(ext)
        if source_type is None:
            raise UnsupportedFormatError(ext or filename)

        content_hash = "sha256:" + hashlib.sha256(file_bytes).hexdigest()
        result = await self._create_and_run(
            name=filename,
            collection_name=collection_name,
            content_hash=content_hash,
            source=file_bytes,
            source_type=source_type,
            tags=tags,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunker=chunker,
            enable_graph=enable_graph,
            force=force,
        )
        return {
            "document_id": result["document_id"],
            "job_id": result["job_id"],
            "status": result["status"],
            "collection": result["collection"],
            "source_name": result["source_name"],
            "source_type": result["source_type"],
            "chunk_count": result["chunk_count"],
        }

    async def ingest_url(
        self,
        url: str,
        collection_name: str,
        *,
        tags: list[str] | None = None,
        chunk_size: int,
        chunk_overlap: int,
        chunker: str | None = None,
        enable_graph: bool = False,
        force: bool = False,
    ) -> dict:
        content_hash = "sha256:" + hashlib.sha256(url.encode("utf-8")).hexdigest()
        result = await self._create_and_run(
            name=url,
            collection_name=collection_name,
            content_hash=content_hash,
            source=url,
            source_type="url",
            tags=tags,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunker=chunker,
            enable_graph=enable_graph,
            force=force,
            source_url=url,
        )
        return {
            "document_id": result["document_id"],
            "job_id": result["job_id"],
            "status": result["status"],
            "collection": result["collection"],
            "source_name": result["source_name"],
            "source_type": result["source_type"],
            "chunk_count": result["chunk_count"],
        }

    async def ingest_text(
        self,
        text: str,
        title: str,
        collection_name: str,
        *,
        tags: list[str] | None = None,
        chunk_size: int,
        chunk_overlap: int,
        chunker: str | None = None,
        enable_graph: bool = False,
        force: bool = False,
        custom_metadata: dict[str, Any] | None = None,
    ) -> dict:
        source_name = title or "text-ingest"
        content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        result = await self._create_and_run(
            name=source_name,
            collection_name=collection_name,
            content_hash=content_hash,
            source=text,
            source_type="text",
            tags=tags,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunker=chunker,
            enable_graph=enable_graph,
            force=force,
            custom_metadata=custom_metadata,
        )
        return {
            "document_id": result["document_id"],
            "status": result["status"],
            "chunk_count": result["chunk_count"],
            "collection": result["collection"],
        }

    async def retry_document(self, document_id: str) -> dict:
        doc = await self.document_repo.get(document_id)
        if doc is None:
            raise DocumentNotFoundError(document_id)

        collection_name = await self.collection_service.resolve_name(doc.collection_id)
        now = datetime.datetime.utcnow()
        job = await self.job_repo.create(
            document_id=doc.id,
            collection_id=doc.collection_id,
            status="queued",
            stage="queued",
            started_at=now,
        )

        # Remove previously-stored chunks (DB + vector + bm25) before re-running.
        old_chunks = await self.document_repo.get_chunks(document_id)
        old_ids = [c.id for c in old_chunks]
        if old_ids:
            try:
                await self.comp.vector_store.delete(collection_name, old_ids)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "retry_vector_delete_failed", document=document_id, error=str(exc)
                )
            try:
                await self.comp.bm25_index.remove(collection_name, old_ids)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "retry_bm25_remove_failed", document=document_id, error=str(exc)
                )
            await self.chunk_repo.delete_many(old_ids)

        # Reconstruct the original source.
        if doc.source_type == "url" and doc.source_url:
            source = doc.source_url
            source_type = "url"
        elif old_chunks:
            source = "\n".join(c.text for c in old_chunks)
            source_type = "text"
        else:
            raise RAGError(
                f"Cannot retry document {document_id}: no source or chunks available"
            )

        doc.status = "pending"
        doc.chunk_count = 0
        doc.token_count = 0
        try:
            options = IngestOptions(
                chunker=None,
                chunk_size=settings.default_chunk_size,
                chunk_overlap=settings.default_chunk_overlap,
                enable_graph=False,
                tags=doc.tags,
                custom_metadata=doc.doc_metadata or {},
            )
            count = await self._run(doc, collection_name, source, source_type, options)
        except Exception as exc:  # noqa: BLE001
            doc.status = "error"
            doc.updated_at = datetime.datetime.utcnow()
            job.status = "error"
            job.error_message = str(exc)
            job.completed_at = datetime.datetime.utcnow()
            await self.session.flush()
            if isinstance(exc, RAGError):
                raise
            raise RAGError(str(exc)) from exc

        doc.updated_at = datetime.datetime.utcnow()
        job.status = "success"
        job.stage = "done"
        job.chunks_total = count
        job.chunks_done = count
        job.completed_at = datetime.datetime.utcnow()
        await self.session.flush()

        return {"document_id": doc.id, "job_id": job.id, "status": "success"}

    # ------------------------------------------------------------------ #
    # Shared create + run
    # ------------------------------------------------------------------ #
    async def _create_and_run(
        self,
        *,
        name: str,
        collection_name: str,
        content_hash: str,
        source: bytes | str,
        source_type: str,
        tags: list[str] | None,
        chunk_size: int,
        chunk_overlap: int,
        chunker: str | None,
        enable_graph: bool,
        force: bool,
        source_url: str | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> dict:
        collection_name = await self.collection_service.resolve_name(collection_name)
        collection = await self.collection_repo.get_by_name(collection_name)
        if collection is None:
            raise CollectionNotFoundError(collection_name)

        existing = await self.document_repo.get_by_hash(collection.id, content_hash)
        if existing is not None and not force:
            return {
                "document_id": existing.id,
                "job_id": None,
                "status": "already_exists",
                "chunk_count": existing.chunk_count,
                "collection": collection_name,
                "source_name": existing.name,
                "source_type": existing.source_type,
            }

        now = datetime.datetime.utcnow()
        doc = await self.document_repo.create(
            collection_id=collection.id,
            name=name,
            source_type=source_type,
            source_url=source_url,
            content_hash=content_hash,
            status="pending",
            tags=tags or [],
            doc_metadata=custom_metadata or {},
        )
        job = await self.job_repo.create(
            document_id=doc.id,
            collection_id=collection.id,
            status="queued",
            stage="queued",
            started_at=now,
        )

        try:
            chunks = await self._run(
                doc,
                collection_name,
                source,
                source_type,
                IngestOptions(
                    chunker=chunker,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    enable_graph=enable_graph,
                    tags=tags or [],
                    custom_metadata=custom_metadata or {},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            doc.status = "error"
            doc.updated_at = datetime.datetime.utcnow()
            job.status = "error"
            job.error_message = str(exc)
            job.completed_at = datetime.datetime.utcnow()
            await self.session.flush()
            if isinstance(exc, RAGError):
                raise
            raise RAGError(str(exc)) from exc

        doc.updated_at = datetime.datetime.utcnow()
        job.status = "success"
        job.stage = "done"
        job.chunks_total = chunks
        job.chunks_done = chunks
        job.completed_at = datetime.datetime.utcnow()
        await self.session.flush()

        return {
            "document_id": doc.id,
            "job_id": job.id,
            "status": "success",
            "chunk_count": chunks,
            "collection": collection_name,
            "source_name": name,
            "source_type": source_type,
        }

    # ------------------------------------------------------------------ #
    # Core pipeline
    # ------------------------------------------------------------------ #
    async def _run(
        self,
        doc: Document,
        collection_name: str,
        source: bytes | str,
        source_type: str,
        options: IngestOptions,
    ) -> int:
        parser = resolve_parser(source_type)
        parse_result = await parser.parse(source)
        if not parse_result.text.strip():
            raise EmptyDocumentError(f"Document {doc.id} produced no extractable text")

        chunker = resolve_chunker(
            options.chunker, options.chunk_size, options.chunk_overlap
        )
        chunks = chunker.chunk(
            parse_result.text,
            {**parse_result.metadata, **options.custom_metadata},
        )

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for c in chunks:
            token_count = len(c.text.split())
            c.token_count = token_count
            c.metadata["document_id"] = doc.id
            c.metadata["collection_id"] = doc.collection_id
            c.metadata["source_type"] = source_type
            c.metadata["source_name"] = doc.name
            c.metadata["tags"] = list(options.tags)
            c.metadata["token_count"] = token_count
            c.metadata["created_at"] = now_iso

        vectors = await self.comp.embedder.embed_batch(
            [c.text for c in chunks],
            batch_size=settings.openai_embed_batch_size,
        )

        if vectors:
            await self.comp.vector_store.ensure_collection(
                collection_name, len(vectors[0])
            )
            await self.comp.vector_store.upsert(collection_name, chunks, vectors)
        else:
            logger.warning(
                "embed_empty_skipping_vector_store",
                document=doc.id,
                collection=collection_name,
            )

        await self.comp.bm25_index.add(collection_name, chunks)

        if options.enable_graph and self.comp.graph_retriever is not None:
            try:
                await self.comp.graph_retriever.ingest(chunks)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "graph_ingest_failed", document=doc.id, error=str(exc)
                )

        db_chunks = [self._to_db_chunk(doc, c) for c in chunks]
        await self.chunk_repo.add_many(db_chunks)

        doc.chunk_count = len(chunks)
        doc.token_count = sum(c.token_count for c in chunks)
        doc.status = "success"
        doc.updated_at = datetime.datetime.utcnow()
        await self.session.flush()
        return len(chunks)

    @staticmethod
    def _to_db_chunk(doc: Document, c: TextChunk) -> Chunk:
        db_chunk = Chunk(
            id=c.chunk_id,
            document_id=doc.id,
            collection_id=doc.collection_id,
            chunk_index=c.chunk_index,
            text=c.text,
            start_char=c.start_char,
            end_char=c.end_char,
            token_count=c.token_count,
        )
        db_chunk.chunk_metadata = dict(c.metadata)
        return db_chunk
