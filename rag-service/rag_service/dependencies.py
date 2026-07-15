"""FastAPI dependency providers.

Builds the wired :class:`RAGComponents` once (lazily, cached) and exposes
service factories. Parsers / chunkers are resolved per-call from the factory
because they are cheap and stateless.
"""

from __future__ import annotations

import threading

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rag_service.core.factory import RAGComponents, build_components
from rag_service.db.session import get_db

_components: RAGComponents | None = None
_components_lock = threading.Lock()


def get_components() -> RAGComponents:
    global _components
    if _components is None:
        with _components_lock:
            if _components is None:
                _components = build_components()
    return _components


def reset_components() -> None:
    """Drop the cached components (used by tests / reconfiguration)."""
    global _components
    _components = None


# --------------------------------------------------------------------------- #
# Service factories (constructed per-request; initialization is trivial)
# --------------------------------------------------------------------------- #
def get_collection_service(
    session: AsyncSession = Depends(get_db),
    comp: RAGComponents = Depends(get_components),
):
    from rag_service.services.collection_service import CollectionService

    return CollectionService(session, comp)


def get_document_service(
    session: AsyncSession = Depends(get_db),
    comp: RAGComponents = Depends(get_components),
):
    from rag_service.services.document_service import DocumentService

    return DocumentService(session, comp)


def get_ingest_service(
    session: AsyncSession = Depends(get_db),
    comp: RAGComponents = Depends(get_components),
):
    from rag_service.services.ingest_service import IngestService

    return IngestService(session, comp)


def get_retrieval_service(
    session: AsyncSession = Depends(get_db),
    comp: RAGComponents = Depends(get_components),
):
    from rag_service.services.retrieval_service import RetrievalService

    return RetrievalService(session, comp)
