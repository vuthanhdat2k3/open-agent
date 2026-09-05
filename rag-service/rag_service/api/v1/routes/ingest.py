"""Ingestion endpoints (file / URL / text)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import BaseModel

from rag_service.config import settings
from rag_service.dependencies import get_ingest_service
from rag_service.schemas import IngestFileResponse, IngestTextResponse

router = APIRouter(tags=["ingest"])


class IngestUrlRequest(BaseModel):
    url: str
    collection: str = "default"
    tags: list[str] | None = None
    chunk_size: int = settings.default_chunk_size
    chunk_overlap: int = settings.default_chunk_overlap
    chunker: str | None = None
    enable_graph: bool = False
    force: bool = False


class IngestTextRequest(BaseModel):
    text: str
    title: str
    collection: str = "default"
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    chunk_size: int = settings.default_chunk_size
    chunk_overlap: int = settings.default_chunk_overlap
    chunker: str | None = None
    enable_graph: bool = False
    force: bool = False


def _parse_tags(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"tags must be a JSON array string: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("tags must be a JSON array string")
    return [str(t) for t in data]


async def _ensure_collection(svc: object, name: str) -> None:
    """Idempotently ensure the target collection exists before ingest."""
    from rag_service.services.collection_service import CollectionService

    cs = CollectionService(svc.session, svc.comp)  # type: ignore[attr-defined]
    existing = await cs.get_collection(name)
    if existing is None:
        await cs.create_collection(name)


@router.post("/ingest/file", status_code=status.HTTP_202_ACCEPTED)
async def ingest_file(
    file: UploadFile = File(...),
    collection: str = Form("default"),
    tags: str | None = Form(None),
    chunk_size: int = Form(settings.default_chunk_size),
    chunk_overlap: int = Form(settings.default_chunk_overlap),
    chunker: str | None = Form(None),
    enable_graph: bool = Form(False),
    force: bool = Form(False),
    svc=Depends(get_ingest_service),
) -> IngestFileResponse:
    await _ensure_collection(svc, collection)
    raw = await file.read()
    tag_list = _parse_tags(tags)
    data = await svc.ingest_file(
        raw,
        file.filename or "upload",
        collection,
        tags=tag_list,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunker=chunker,
        enable_graph=enable_graph,
        force=force,
    )
    return IngestFileResponse(**data)


@router.post("/ingest/url", status_code=status.HTTP_202_ACCEPTED)
async def ingest_url(
    payload: IngestUrlRequest,
    svc=Depends(get_ingest_service),
) -> IngestFileResponse:
    await _ensure_collection(svc, payload.collection)
    data = await svc.ingest_url(
        payload.url,
        payload.collection,
        tags=payload.tags,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        chunker=payload.chunker,
        enable_graph=payload.enable_graph,
        force=payload.force,
    )
    return IngestFileResponse(**data)


@router.post("/ingest/text", status_code=status.HTTP_201_CREATED)
async def ingest_text(
    payload: IngestTextRequest,
    svc=Depends(get_ingest_service),
) -> IngestTextResponse:
    await _ensure_collection(svc, payload.collection)
    data = await svc.ingest_text(
        payload.text,
        payload.title,
        payload.collection,
        tags=payload.tags,
        custom_metadata=payload.metadata,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        chunker=payload.chunker,
        enable_graph=payload.enable_graph,
        force=payload.force,
    )
    return IngestTextResponse(**data)
