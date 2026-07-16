from collections.abc import AsyncGenerator
import asyncio

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings
from app.db.base import Base


settings = get_settings()

engine = create_async_engine(settings.db_url, echo=False, future=True)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Apply database schema via Alembic (production path).

    For an existing database this runs pending migrations (e.g. restructuring
    agent_memories) without data loss. For a brand-new, empty database we
    bootstrap via create_all once, then stamp it at the current head so future
    `alembic upgrade` calls apply incrementally.
    """
    from app import models  # noqa: F401  (register models on Base.metadata)
    from sqlalchemy import text as _text

    # Detect whether this is a fresh database.
    async with engine.begin() as conn:
        result = await conn.execute(
            _text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='agents'"
            )
        )
        has_agents = result.first() is not None

    # Import alembic late to avoid import cost when not needed.
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")

    if not has_agents:
        # Fresh DB: create everything from models, then stamp at head.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await asyncio.to_thread(command.stamp, cfg, "head")
    else:
        await asyncio.to_thread(command.upgrade, cfg, "head")
