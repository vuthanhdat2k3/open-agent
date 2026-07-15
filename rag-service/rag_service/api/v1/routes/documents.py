"""Document management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from rag_service.dependencies import get_document_service, get_ingest_service
from rag_service.schemas import (
    DocumentDetail,
    DocumentListResponse,
    DocumentRead,
    RetryResponse,
)

router = APIRouter(tags=["documents"])


@router.get("/documents")
async def list_documents(
    collection_id: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    svc=Depends(get_document_service),
) -> DocumentListResponse:
    total, items = await svc.list_documents(
        collection_id=collection_id,
        status=status,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        total=total, items=[DocumentRead(**d) for d in items]
    )


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    svc=Depends(get_document_service),
) -> DocumentDetail:
    data = await svc.get_document(document_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id!r} not found")
    return DocumentDetail(**data)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    svc=Depends(get_document_service),
) -> Response:
    await svc.delete_document(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_document(
    document_id: str,
    svc=Depends(get_ingest_service),
) -> RetryResponse:
    data = await svc.retry_document(document_id)
    return RetryResponse(**data)
