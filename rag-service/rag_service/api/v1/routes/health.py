"""Health-check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from rag_service import __version__
from rag_service.core.logging import logger
from rag_service.db.base import get_sessionmaker
from rag_service.dependencies import get_components

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness + component readiness probe (non-fatal)."""
    comp = get_components()
    components = {
        "vector_store": "unavailable",
        "bm25_index": "unavailable",
        "embedder": "unavailable",
        "database": "unavailable",
    }

    try:
        components["vector_store"] = "ok" if comp.vector_store is not None else "unavailable"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("health_vector_store_check_failed", error=str(exc))

    try:
        components["bm25_index"] = "ok" if comp.bm25_index is not None else "unavailable"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("health_bm25_check_failed", error=str(exc))

    try:
        components["embedder"] = "ok" if comp.embedder is not None else "unavailable"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("health_embedder_check_failed", error=str(exc))

    try:
        maker = get_sessionmaker()
        async with maker() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("health_database_check_failed", error=str(exc))

    return {"status": "ok", "version": __version__, "components": components}
