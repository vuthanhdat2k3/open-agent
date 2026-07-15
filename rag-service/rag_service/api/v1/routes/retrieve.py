"""Retrieval endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rag_service.dependencies import get_retrieval_service
from rag_service.schemas import RetrieveRequest, RetrieveResponse

router = APIRouter(tags=["retrieve"])


@router.post("/retrieve")
async def retrieve(
    payload: RetrieveRequest,
    svc=Depends(get_retrieval_service),
) -> RetrieveResponse:
    filters = payload.filters.model_dump() if payload.filters is not None else None
    results, debug = await svc.search(
        query=payload.query,
        collection_name=payload.collection,
        top_k=payload.top_k,
        candidate_k=payload.candidate_k,
        filters=filters,
        enable_graph=payload.enable_graph,
        debug=payload.debug,
    )
    return RetrieveResponse(query=payload.query, results=results, debug=debug)
