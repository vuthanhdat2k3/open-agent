import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.base import Base

settings = get_settings()

engine_kwargs = {"echo": False, "future": True}
if "postgresql" in settings.db_url:
    engine_kwargs["connect_args"] = {"statement_cache_size": 0}

engine = create_async_engine(settings.db_url, **engine_kwargs)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def _has_table(conn: AsyncConnection, table_name: str) -> bool:
    return await conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table(table_name))


async def init_db() -> None:
    """Apply database schema via Alembic (production path).

    For an existing database with alembic_version this runs pending migrations.
    For a fresh database or DB initialized via create_all, we create missing
    tables and stamp at head so future upgrades apply incrementally.
    """
    from app import models  # noqa: F401  (register models on Base.metadata)

    async with engine.begin() as conn:
        has_agents = await _has_table(conn, "agents")
        has_alembic = await _has_table(conn, "alembic_version")

    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%"))

    if not has_agents or not has_alembic:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await asyncio.to_thread(command.stamp, cfg, "head")
    else:
        await asyncio.to_thread(command.upgrade, cfg, "head")
