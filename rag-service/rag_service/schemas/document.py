"""Document & chunk request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_index: int
    text: str
    start_char: int
    end_char: int
    token_count: int


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    collection_id: str
    name: str
    source_type: str
    source_url: str | None = None
    content_hash: str
    status: str
    chunk_count: int
    token_count: int
    tags: list[str] = []
    metadata: dict = {}
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentRead):
    chunks: list[ChunkRead] = []


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentRead]


class IngestFileResponse(BaseModel):
    document_id: str
    job_id: str | None = None
    status: str
    collection: str
    source_name: str | None = None
    source_type: str | None = None
    chunk_count: int | None = None


class IngestTextResponse(BaseModel):
    document_id: str
    status: str
    chunk_count: int
    collection: str


class RetryResponse(BaseModel):
    document_id: str
    job_id: str
    status: str


class JobProgress(BaseModel):
    stage: str | None = None
    chunks_processed: int = 0
    chunks_total: int = 0


class JobStatusResponse(BaseModel):
    job_id: str
    document_id: str | None = None
    status: str
    progress: JobProgress = Field(default_factory=JobProgress)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    errors: list[dict] = []
