"""Collection request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536


class CollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    embedding_model: str
    embedding_dimensions: int
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime
