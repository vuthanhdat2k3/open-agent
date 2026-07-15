"""Seed the default collection (and any bootstrap data)."""

from __future__ import annotations

from rag_service.db.base import get_sessionmaker
from rag_service.dependencies import get_components
from rag_service.services.collection_service import CollectionService


async def seed_default_collection() -> None:
    async with get_sessionmaker()() as session:
        await CollectionService(session, get_components()).ensure_default()
        await session.commit()
