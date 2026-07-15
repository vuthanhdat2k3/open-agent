"""Async DB session dependency helper."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from rag_service.db.base import get_sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an :class:`AsyncSession`. Commits on success, rolls back on error."""
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
