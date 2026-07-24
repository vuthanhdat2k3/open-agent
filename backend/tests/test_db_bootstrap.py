from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import session as db_session
from app.db.base import utc_now


def test_utc_now_matches_timezone_naive_database_columns() -> None:
    assert utc_now().tzinfo is None


@pytest.mark.asyncio
async def test_init_db_bootstraps_a_fresh_database(tmp_path: Path, monkeypatch) -> None:
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    monkeypatch.setattr(db_session, "engine", test_engine)

    try:
        await db_session.init_db()

        async with test_engine.connect() as conn:
            table_names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

        assert "agents" in table_names
        assert "agent_memories" in table_names
        assert "alembic_version" in table_names
    finally:
        await test_engine.dispose()
