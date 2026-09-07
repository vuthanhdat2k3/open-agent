from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UploadedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    content_type: str
    size: int
    status: str
    visibility: str = "personal"
    collection: str | None = None
    error: str | None = None
    created_by_user_id: str | None = None
    creator_email: str | None = None
    creator_name: str | None = None
    created_at: datetime
    updated_at: datetime


class IngestRequest(BaseModel):
    collection: str = "default"
    chunk_size: int = Field(default=800, ge=1, le=10000)
    chunk_overlap: int = Field(default=150, ge=0, le=5000)
    tags: list[str] = Field(default_factory=list, max_length=100)


class IngestJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    file_id: str
    status: str
    deduplicated: bool = False
    attempt_count: int
    max_attempts: int
    rag_document_id: str | None = None
    chunk_count: int | None = None
    warnings: list = Field(default_factory=list)
    error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime
    updated_at: datetime


class IngestJobRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    status: str
    attempt_count: int
    max_attempts: int
    rag_document_id: str | None = None
    chunk_count: int | None = None
    warnings: list = Field(default_factory=list)
    error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime
    updated_at: datetime
