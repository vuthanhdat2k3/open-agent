"""Collection management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from rag_service.dependencies import get_collection_service
from rag_service.schemas import CollectionCreate, CollectionRead

router = APIRouter(tags=["collections"])


@router.get("/collections")
async def list_collections(
    svc=Depends(get_collection_service),
) -> list[CollectionRead]:
    collections = await svc.list_collections()
    return [CollectionRead(**c) for c in collections]


@router.post("/collections", status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreate,
    svc=Depends(get_collection_service),
) -> CollectionRead:
    data = await svc.create_collection(
        payload.name,
        payload.description,
        payload.embedding_model,
        payload.embedding_dimensions,
    )
    return CollectionRead(**data)


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    svc=Depends(get_collection_service),
) -> CollectionRead:
    data = await svc.get_collection(collection_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id!r} not found")
    return CollectionRead(**data)


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    svc=Depends(get_collection_service),
) -> Response:
    await svc.delete_collection(collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
