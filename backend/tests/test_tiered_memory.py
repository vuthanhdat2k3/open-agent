from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.memory.tiers import compact_tiered_memory
from app.db.base import Base
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_compact_tiered_memory_within_hot_window(async_session_factory):
    async with async_session_factory() as db:
        m1 = Message(org_id="org-tier", session_id="s-100", role="user", content="Hello", position=1)
        m2 = Message(org_id="org-tier", session_id="s-100", role="assistant", content="Hi there!", position=2)
        db.add_all([m1, m2])
        await db.commit()

        mock_model = Model(name="dummy-model", provider_id="p-1")
        mock_provider = Provider(name="dummy", base_url="http://dummy")

        res = await compact_tiered_memory(
            session_id="s-100",
            db=db,
            agent_model=mock_model,
            provider=mock_provider,
            hot_window=4,
        )

        assert "Hello" in res["hot"]
        assert "Hi there!" in res["hot"]
        assert res["warm"] == ""
