"""Central v1 API router.

Exposes ``api_router`` (an :class:`fastapi.APIRouter`) that bundles the health,
collections, documents, ingest and retrieve sub-routers, registers global
exception handlers, and enforces the optional ``X-API-Key`` admin guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from rag_service.config import settings
from rag_service.exceptions import RAGError

# --------------------------------------------------------------------------- #
# Auth dependency
# --------------------------------------------------------------------------- #
async def api_key_auth(request: Request) -> None:
    """Require the admin ``X-API-Key`` header when ``settings.api_key`` is set.

    When ``settings.api_key`` is empty the guard is a no-op except in
    ``RAG_ENV=production`` (the Dockerfile default), which fails closed
    instead of silently serving the collection/document/ingest admin API
    unauthenticated.
    """
    if settings.api_key:
        provided = request.headers.get("X-API-Key")
        if provided != settings.api_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing X-API-Key",
                headers={"WWW-Authenticate": "X-API-Key"},
            )
        return
    if settings.env == "production":
        raise HTTPException(
            status_code=503,
            detail="RAG_API_KEY is not configured — refusing to serve the admin API unauthenticated outside development",
        )


# --------------------------------------------------------------------------- #
api_router = APIRouter(
    dependencies=[Depends(api_key_auth)],
    responses={
        401: {"description": "Unauthorized — missing/invalid X-API-Key"},
        500: {"description": "Internal error"},
    },
)


# --------------------------------------------------------------------------- #
# Exception handlers
# --------------------------------------------------------------------------- #
async def rag_error_handler(request: Request, exc: RAGError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc), "detail": None}},
    )


# --------------------------------------------------------------------------- #
# Sub-routers
# --------------------------------------------------------------------------- #
from rag_service.api.v1.routes.health import router as health_router  # noqa: E402
from rag_service.api.v1.routes.collections import router as collections_router  # noqa: E402
from rag_service.api.v1.routes.documents import router as documents_router  # noqa: E402
from rag_service.api.v1.routes.ingest import router as ingest_router  # noqa: E402
from rag_service.api.v1.routes.retrieve import router as retrieve_router  # noqa: E402

api_router.include_router(health_router)
api_router.include_router(collections_router)
api_router.include_router(documents_router)
api_router.include_router(ingest_router)
api_router.include_router(retrieve_router)
