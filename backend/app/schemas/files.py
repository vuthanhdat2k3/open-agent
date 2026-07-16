from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UploadedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    content_type: str
    size: int
    status: str
    collection: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class IngestRequest(BaseModel):
    collection: str = "default"
    chunk_size: int = 800
    chunk_overlap: int = 150
    tags: list[str] = []


class IngestResult(BaseModel):
    ok: bool
    result: str
    document_id: Optional[str] = None
