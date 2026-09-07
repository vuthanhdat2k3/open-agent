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


@pytest.mark.asyncio
async def test_update_session_execution_policy_full_access(client, async_session_factory):
    token, org_id = _register(client)
    session_id = "session-update-policy"
    agent_id = "agent-update-policy"

    async with async_session_factory() as db:
        db.add(Agent(id=agent_id, org_id=org_id, name="Policy test agent"))
        db.add(Session(id=session_id, org_id=org_id, agent_id=agent_id, title="Policy me", execution_policy="manual"))
        await db.commit()

    response = client.patch(
        f"/api/sessions/{session_id}",
        json={"execution_policy": "full-access"},
        headers={"Authorization": f"Bearer {token}", "X-Org-Id": org_id},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["execution_policy"] == "full-access"



@pytest.mark.asyncio
async def test_clear_session_messages(client, async_session_factory):
    token, org_id = _register(client)
    session_id = "session-clear-test"
    agent_id = "agent-clear-test"

    async with async_session_factory() as db:
        db.add(Agent(id=agent_id, org_id=org_id, name="Clear test agent"))
        db.add(Session(id=session_id, org_id=org_id, agent_id=agent_id, title="Clear me"))
        db.add(
            Message(
                id="msg-clear-1",
                org_id=org_id,
                session_id=session_id,
                role="user",
                content="hello world",
                position=0,
            )
        )
        db.add(
            SessionMemory(
                id="mem-clear-1",
                org_id=org_id,
                session_id=session_id,
                key="topic",
                value="testing",
            )
        )
        db.add(
            SessionEvent(
                id="ev-clear-1",
                org_id=org_id,
                session_id=session_id,
                seq=1,
                type=slog.USER_MESSAGE,
                data={"content": "hello world"},
            )
        )
        await db.commit()

    response = client.post(
        f"/api/sessions/{session_id}/clear",
        headers={"Authorization": f"Bearer {token}", "X-Org-Id": org_id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True

    async with async_session_factory() as db:
        # Session itself still exists
        assert await db.scalar(select(Session).where(Session.id == session_id)) is not None
        # But all messages, memory, and events are wiped clean
        assert await db.scalar(select(Message).where(Message.session_id == session_id)) is None
        assert await db.scalar(select(SessionMemory).where(SessionMemory.session_id == session_id)) is None
        assert await db.scalar(select(SessionEvent).where(SessionEvent.session_id == session_id)) is None


@pytest.mark.asyncio
async def test_compact_session_endpoints(client, async_session_factory):
    token, org_id = _register(client)
    session_id = "session-compact-test"
    agent_id = "agent-compact-test"

    async with async_session_factory() as db:
        db.add(Agent(id=agent_id, org_id=org_id, name="Compact test agent"))
        db.add(Session(id=session_id, org_id=org_id, agent_id=agent_id, title="Compact me"))
        # Add 6 conversation turns
        for i in range(6):
            role = "user" if i % 2 == 0 else "assistant"
            db.add(
                Message(
                    id=f"msg-compact-{i}",
                    org_id=org_id,
                    session_id=session_id,
                    role=role,
                    content=f"Message turn {i} with some content to compress",
                    position=i,
                )
            )
            db.add(
                SessionEvent(
                    id=f"ev-compact-{i}",
                    org_id=org_id,
                    session_id=session_id,
                    seq=i + 1,
                    type=slog.USER_MESSAGE if role == "user" else slog.ASSISTANT_MESSAGE,
                    data={"content": f"Message turn {i} with some content to compress"},
                )
            )
        await db.commit()

    response = client.post(
        f"/api/sessions/{session_id}/compact",
        headers={"Authorization": f"Bearer {token}", "X-Org-Id": org_id},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["compacted"] is True
    assert len(data["summary"]) > 0

    async with async_session_factory() as db:
        # Check that COMPACTION_SUMMARY event was created
        compaction_event = await db.scalar(
            select(SessionEvent).where(
                SessionEvent.session_id == session_id,
                SessionEvent.type == slog.COMPACTION_SUMMARY,
            )
        )
        assert compaction_event is not None
        assert "surface_op" in compaction_event.data

        # Check messages table preserves all older messages PLUS the compaction marker (DSH append-only pattern)
        msgs = (await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.position)
        )).scalars().all()
        # Original 6 messages + 1 compaction marker = 7 total messages preserved!
        assert len(msgs) == 7
        compaction_msg = next((m for m in msgs if m.role == "compaction" or (m.meta and m.meta.get("is_compaction"))), None)
        assert compaction_msg is not None
        assert compaction_msg.meta.get("is_compaction") is True
        assert compaction_msg.meta.get("shadowed_messages_count") == 4
        # Verify older messages 0..3 are preserved before the marker
        assert msgs[0].id == "msg-compact-0"
        assert msgs[3].id == "msg-compact-3"
        # Marker is at index 4
        assert msgs[4].id == compaction_msg.id
        # Hot messages 4..5 are preserved after the marker
        assert msgs[5].id == "msg-compact-4"
        assert msgs[6].id == "msg-compact-5" 
