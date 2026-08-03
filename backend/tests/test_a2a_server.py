from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.a2a.card import generate_agent_card
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.agent import Agent


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    async def _override_redis():
        yield None

    from app.core.quota.dependencies import _redis_client
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_redis_client] = _override_redis
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_agent_card_opt_in_filtering(async_session_factory):
    async with async_session_factory() as db_session:
        agent_hidden = Agent(
            org_id="org-card",
            name="Private Agent",
            tools=["memory_recall"],
            a2a_exposed=False,
        )
        agent_exposed = Agent(
            org_id="org-card",
            name="Public Agent",
            tools=["web_search"],
            a2a_exposed=True,
        )
        db_session.add_all([agent_hidden, agent_exposed])
        await db_session.commit()

        card = generate_agent_card([agent_hidden, agent_exposed], host_url="https://example.com")
        agents = card.get("agents", [])
        assert len(agents) == 1
        assert agents[0]["id"] == agent_exposed.id
        assert agents[0]["name"] == "Public Agent"
        assert "web_search" in agents[0]["skills"]


@pytest.mark.asyncio
async def test_a2a_unauthenticated_request(client: TestClient):
    resp = client.get("/api/a2a/agent-card")
    assert resp.status_code == 401
