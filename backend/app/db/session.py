import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

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

    For an existing database with alembic_version this runs pending migrations.
    For a fresh database or DB initialized via create_all, we create missing
    tables and stamp at head so future upgrades apply incrementally.
    """
    from sqlalchemy import text as _text

    from app import models  # noqa: F401  (register models on Base.metadata)

    async with engine.begin() as conn:
        res_agents = await conn.execute(
            _text("SELECT name FROM sqlite_master WHERE type='table' AND name='agents'")
        )
        has_agents = res_agents.first() is not None

        res_alembic = await conn.execute(
            _text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        )
        has_alembic = res_alembic.first() is not None

    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")

    if not has_agents or not has_alembic:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await asyncio.to_thread(command.stamp, cfg, "head")
    else:
        await asyncio.to_thread(command.upgrade, cfg, "head")
