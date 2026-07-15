"""Retrieval request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrieveFilters(BaseModel):
    source_type: str | None = None
    tags: list[str] | None = None
    document_id: str | None = None


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    collection: str = "default"
    top_k: int = Field(default=5, ge=1, le=20)
    candidate_k: int = Field(default=50, ge=1, le=200)
    enable_graph: bool = False
    filters: RetrieveFilters | None = None
    debug: bool = False


class RetrievalResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    document_id: str
    text: str
    score: float
    rank: int
    source_type: str
    metadata: dict = {}
    highlights: list[str] = []


class RetrieveDebug(BaseModel):
    bm25_candidates: int = 0
    semantic_candidates: int = 0
    rrf_k: int = 60
    embed_latency_ms: float = 0.0
    bm25_latency_ms: float = 0.0
    semantic_latency_ms: float = 0.0
    rrf_latency_ms: float = 0.0
    total_latency_ms: float = 0.0


class RetrieveResponse(BaseModel):
    query: str
    results: list[RetrievalResult]
    debug: RetrieveDebug | None = None
