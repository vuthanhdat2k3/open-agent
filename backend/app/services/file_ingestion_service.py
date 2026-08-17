from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import timedelta

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import utc_now
from app.models.file_ingest_job import FileIngestJob
from app.models.files import UploadedFile
from app.models.outbox import OutboxEvent
from app.services.rag_ingest_client import RagIngestClient, RagIngestError


ACTIVE = {"queued", "processing", "retrying"}
TERMINAL = {"succeeded", "failed", "dead_letter"}


def _idempotency_key(record: UploadedFile, collection: str, chunk_size: int, chunk_overlap: int, tags: list[str]) -> str:
    source_hash = record.file_sha256 or hashlib.sha256(
        f"{record.org_id}:{record.stored_path}:{record.size}".encode()
    ).hexdigest()
    raw = "|".join(
        [record.org_id, source_hash, collection, str(chunk_size), str(chunk_overlap), ",".join(sorted(set(tags))), "v1"]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class FileIngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def create_job(
        self, org_id: str, file_id: str, user_id: str | None, *, collection: str,
        chunk_size: int, chunk_overlap: int, tags: list[str], correlation_id: str,
    ) -> tuple[FileIngestJob, bool]:
        record = await self.db.scalar(
            select(UploadedFile).where(UploadedFile.id == file_id, UploadedFile.org_id == org_id)
        )
        if record is None:
            raise FileNotFoundError("file not found")
        key = _idempotency_key(record, collection, chunk_size, chunk_overlap, tags)
        active = await self.db.scalar(
            select(FileIngestJob).where(FileIngestJob.file_id == file_id, FileIngestJob.status.in_(ACTIVE))
        )
        if active:
            if active.idempotency_key != key:
                raise FileExistsError("another ingestion is already active for this file")
            return active, True
        completed = await self.db.scalar(
            select(FileIngestJob).where(
                FileIngestJob.file_id == file_id,
                FileIngestJob.idempotency_key == key,
                FileIngestJob.status == "succeeded",
            ).order_by(FileIngestJob.created_at.desc())
        )
        if completed:
            return completed, True
        job = FileIngestJob(
            org_id=org_id, file_id=file_id, created_by_user_id=user_id,
            status="queued", idempotency_key=key, collection=collection,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            tags=sorted(set(tags)), max_attempts=self.settings.file_ingest_max_attempts,
            correlation_id=correlation_id,
        )
        self.db.add(job)
        await self.db.flush()
        self.db.add(OutboxEvent(
            event_type="file.ingest.requested", aggregate_type="file_ingest_job",
            aggregate_id=job.id, org_id=org_id, user_id=user_id,
            correlation_id=correlation_id, payload={"job_id": job.id, "correlation_id": correlation_id},
            dedupe_key=f"file-ingest:{job.id}:0",
        ))
        record.status = "queued"
        record.collection = collection
        record.error = None
        await self.db.commit()
        await self.db.refresh(job)
        return job, False

    async def process_job(self, job_id: str, worker_id: str) -> None:
        job = await self.db.scalar(
            select(FileIngestJob).where(FileIngestJob.id == job_id).with_for_update()
        )
        if job is None or job.status in TERMINAL:
            return
        now = utc_now()
        if job.status == "processing" and job.lease_expires_at and job.lease_expires_at > now:
            return
        job.status = "processing"
        job.attempt_count += 1
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=self.settings.file_ingest_lease_seconds)
        job.started_at = job.started_at or now
        await self.db.commit()
        record = await self.db.get(UploadedFile, job.file_id)
        if record is None or record.org_id != job.org_id:
            await self._finish_failure(job, "FILE_NOT_FOUND", "source file no longer exists", retryable=False, worker_id=worker_id)
            return
        body = None
        try:
            body = await asyncio.to_thread(self._download, record.stored_path)
            result = await RagIngestClient(self.settings).ingest(
                body, filename=record.original_name, content_type=record.content_type,
                collection=job.collection, chunk_size=job.chunk_size, chunk_overlap=job.chunk_overlap,
                tags=job.tags, correlation_id=job.correlation_id,
            )
            current = await self.db.scalar(select(FileIngestJob).where(
                FileIngestJob.id == job.id,
                FileIngestJob.status == "processing",
                FileIngestJob.lease_owner == worker_id,
            ))
            if current is None:
                return
            job.status = "succeeded"
            job.rag_document_id = result.document_id
            job.chunk_count = result.chunk_count
            job.source_type = result.provenance.get("source_type")
            job.parser_name = result.provenance.get("parser_name")
            job.parser_version = result.provenance.get("parser_version")
            job.pdf_classification = result.provenance.get("pdf_classification")
            job.classification_confidence = result.provenance.get("classification_confidence")
            job.ocr_engine = result.provenance.get("ocr_engine")
            job.warnings = result.provenance.get("warnings") or []
            job.error_code = None
            job.error_detail = None
            job.completed_at = utc_now()
            job.lease_owner = None
            job.lease_expires_at = None
            record.status = "ingested"
            record.error = None
            await self.db.commit()
        except RagIngestError as exc:
            await self._finish_failure(job, exc.code, exc.detail, retryable=exc.retryable, worker_id=worker_id)
        except (ClientError, OSError) as exc:
            await self._finish_failure(job, "OBJECT_STORE_UNAVAILABLE", "object storage request failed", retryable=True, worker_id=worker_id)
        except Exception:
            await self._finish_failure(job, "INGEST_FAILED", "file ingestion failed", retryable=False, worker_id=worker_id)
        finally:
            if body is not None:
                await asyncio.to_thread(body.close)

    def _download(self, key: str):
        import boto3

        client = boto3.client(
            "s3", endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
        )
        return client.get_object(Bucket=self.settings.s3_bucket, Key=key)["Body"]

    async def _finish_failure(
        self, job: FileIngestJob, code: str, detail: str, *, retryable: bool, worker_id: str | None = None
    ) -> None:
        if worker_id is not None:
            current = await self.db.scalar(select(FileIngestJob).where(
                FileIngestJob.id == job.id,
                FileIngestJob.status == "processing",
                FileIngestJob.lease_owner == worker_id,
            ))
            if current is None:
                return
        job.error_code = code
        job.error_detail = detail[:1000]
        job.lease_owner = None
        job.lease_expires_at = None
        should_retry = retryable and job.attempt_count < job.max_attempts
        if should_retry:
            delay = min(
                self.settings.file_ingest_retry_base_seconds * (2 ** max(job.attempt_count - 1, 0)),
                self.settings.file_ingest_retry_max_seconds,
            ) + random.uniform(0, 2)
            job.status = "retrying"
            job.available_at = utc_now() + timedelta(seconds=delay)
        else:
            job.status = "dead_letter" if retryable else "failed"
            job.completed_at = utc_now()
        record = await self.db.get(UploadedFile, job.file_id)
        if record is not None:
            record.status = "error" if job.status in TERMINAL else "retrying"
            record.error = job.error_detail
        await self.db.commit()

    async def schedule_due_retries(self) -> int:
        now = utc_now()
        jobs = list((await self.db.scalars(
            select(FileIngestJob).where(FileIngestJob.status == "retrying", FileIngestJob.available_at <= now).limit(100)
        )).all())
        for job in jobs:
            job.status = "queued"
            self.db.add(OutboxEvent(
                event_type="file.ingest.requested", aggregate_type="file_ingest_job",
                aggregate_id=job.id, org_id=job.org_id, user_id=job.created_by_user_id,
                correlation_id=job.correlation_id, payload={"job_id": job.id, "correlation_id": job.correlation_id},
                dedupe_key=f"file-ingest:{job.id}:{job.attempt_count}",
            ))
            record = await self.db.get(UploadedFile, job.file_id)
            if record:
                record.status = "queued"
        await self.db.commit()
        return len(jobs)

    async def recover_expired(self) -> int:
        jobs = list((await self.db.scalars(select(FileIngestJob).where(
            FileIngestJob.status == "processing", FileIngestJob.lease_expires_at < utc_now()
        ).limit(100))).all())
        for job in jobs:
            await self._finish_failure(job, "WORKER_LEASE_EXPIRED", "worker lease expired", retryable=True)
        return len(jobs)
