"""SQLAlchemy async engine and metadata base."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from rag_service.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """Lazily create the async engine (singleton)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.db_url,
            echo=settings.db_echo,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def init_db() -> None:
    """Create all tables. Used on startup so the service runs without Alembic CLI.

    (A full Alembic migration set is provided under ``alembic/`` for production;
    this guarantees first-run correctness with zero external tooling.)
    """
    from rag_service import models  # noqa: F401  (register mappers)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
