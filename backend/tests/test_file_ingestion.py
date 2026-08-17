from __future__ import annotations

import io

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.file_ingest_job import FileIngestJob
from app.models.files import UploadedFile
from app.models.outbox import OutboxEvent
from app.services.file_ingestion_service import FileIngestionService
from app.services.rag_ingest_client import RagIngestClient, RagIngestError


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_job_is_idempotent_and_creates_outbox(async_session_factory):
    async with async_session_factory() as db:
        db.add(UploadedFile(
            id="file-1", org_id="org-1", original_name="guide.pdf", filename="guide.pdf",
            stored_path="org-1/guide.pdf", size=10, file_sha256="a" * 64,
        ))
        await db.commit()
        service = FileIngestionService(db)
        first, deduplicated = await service.create_job(
            "org-1", "file-1", "user-1", collection="default", chunk_size=800,
            chunk_overlap=150, tags=["docs"], correlation_id="corr-1",
        )
        second, deduplicated_again = await service.create_job(
            "org-1", "file-1", "user-1", collection="default", chunk_size=800,
            chunk_overlap=150, tags=["docs"], correlation_id="corr-2",
        )
        assert deduplicated is False
        assert deduplicated_again is True
        assert second.id == first.id
        assert len((await db.scalars(select(OutboxEvent))).all()) == 1


@pytest.mark.asyncio
async def test_rag_client_rejects_false_success(monkeypatch):
    class MockClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return httpx.Response(200, json={"status": "success", "document_id": "", "chunk_count": 0})

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    settings = type("Settings", (), {
        "rag_service_url": "http://rag-service:8100", "rag_api_key": "secret",
        "rag_ingest_connect_timeout_seconds": 1.0, "rag_ingest_read_timeout_seconds": 2.0,
    })()
    with pytest.raises(RagIngestError, match="no stored chunks"):
        await RagIngestClient(settings).ingest(
            io.BytesIO(b"x"), filename="a.pdf", content_type="application/pdf",
            collection="default", chunk_size=800, chunk_overlap=150, tags=[], correlation_id="c",
        )


@pytest.mark.asyncio
async def test_transient_failure_moves_job_to_retrying(async_session_factory, monkeypatch):
    async with async_session_factory() as db:
        db.add(UploadedFile(
            id="file-2", org_id="org-2", original_name="guide.pdf", filename="guide.pdf",
            stored_path="org-2/guide.pdf", size=10, file_sha256="b" * 64,
        ))
        await db.commit()
        service = FileIngestionService(db)
        job, _ = await service.create_job(
            "org-2", "file-2", None, collection="default", chunk_size=800,
            chunk_overlap=150, tags=[], correlation_id="corr-2",
        )
        async def fail(*_args, **_kwargs):
            raise RagIngestError("RAG_UNAVAILABLE", "temporary", retryable=True)

        monkeypatch.setattr("app.services.file_ingestion_service.RagIngestClient.ingest", fail)
        monkeypatch.setattr(service, "_download", lambda _key: io.BytesIO(b"x"))
        await service.process_job(job.id, "worker-1")
        refreshed = await db.get(FileIngestJob, job.id)
        assert refreshed.status == "retrying"
        assert refreshed.error_code == "RAG_UNAVAILABLE"
        assert refreshed.attempt_count == 1
