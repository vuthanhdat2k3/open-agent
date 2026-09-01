from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import session_log as slog
from app.core.quota.dependencies import _redis_client
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.agent import Agent
from app.models.memory import SessionMemory
from app.models.message import Message
from app.models.session import Session
from app.models.session_event import SessionEvent

PASSWORD = "Secret123!"


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
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

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_redis_client] = _override_redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _register(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": "session-delete@test.com", "password": PASSWORD, "org_name": "Session Delete"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["memberships"][0]["org_id"]


@pytest.mark.asyncio
async def test_delete_session_removes_messages_and_session_memory(client, async_session_factory):
    token, org_id = _register(client)
    session_id = "session-delete-regression"
    agent_id = "agent-delete-regression"

    async with async_session_factory() as db:
        db.add(Agent(id=agent_id, org_id=org_id, name="Delete test agent"))
        db.add(Session(id=session_id, org_id=org_id, agent_id=agent_id, title="Delete me"))
        db.add(
            Message(
                id="message-delete-regression",
                org_id=org_id,
                session_id=session_id,
                role="user",
                content="hello",
                position=0,
            )
        )
        db.add(
            SessionMemory(
                id="memory-delete-regression",
                org_id=org_id,
                session_id=session_id,
                key="preference",
                value="concise",
            )
        )
        db.add(
            SessionEvent(
                id="event-delete-regression",
                org_id=org_id,
                session_id=session_id,
                seq=0,
                type=slog.USER_MESSAGE,
                data={"content": "hello"},
            )
        )
        await db.commit()

    response = client.delete(
        f"/api/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}", "X-Org-Id": org_id},
    )
    assert response.status_code == 200, response.text

    async with async_session_factory() as db:
        assert await db.scalar(select(Session).where(Session.id == session_id)) is None
        assert await db.scalar(select(Message).where(Message.session_id == session_id)) is None
        assert await db.scalar(select(SessionMemory).where(SessionMemory.session_id == session_id)) is None
        assert await db.scalar(select(SessionEvent).where(SessionEvent.session_id == session_id)) is None
