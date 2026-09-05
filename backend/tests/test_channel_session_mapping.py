from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.channels.jobs import process_channel_message
from app.core.execution_policy import ExecutionPolicy
from app.db.base import Base
from app.models.agent import Agent
from app.models.channel import ChannelConnection, ChannelConversation, ChannelMessage
from app.models.organization import Organization
from app.schemas.chat import AgentLoopResult
from app.services.channel_service import ChannelService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_ensure_conversation_session_lifecycle(async_session_factory):
    async with async_session_factory() as db:
        org = Organization(id="org-test-1", name="Test Org", slug="test-org-1")
        db.add(org)
        agent1 = Agent(id="agent-1", org_id="org-test-1", name="Support Bot")
        agent2 = Agent(id="agent-2", org_id="org-test-1", name="Sales Bot")
        db.add_all([agent1, agent2])

        conn = ChannelConnection(
            id="conn-1",
            org_id="org-test-1",
            provider="discord",
            bot_token_enc="enc_token",
            bot_username="SupportDiscordBot",
            status="active",
            config={"execution_policy": ExecutionPolicy.full_access.value},
        )
        db.add(conn)
        await db.commit()

        service = ChannelService(db)

        # 1. First turn: Creates a new session
        session1, is_new1 = await service.ensure_conversation_session(
            org_id="org-test-1",
            connection=conn,
            conversation_id="conv-1001",
            agent=agent1,
            sender_name="Alice",
            force_new=False,
        )
        assert is_new1 is True
        assert session1.org_id == "org-test-1"
        assert session1.agent_id == "agent-1"
        assert session1.execution_policy == ExecutionPolicy.full_access.value
        assert "Alice" in session1.title

        # 2. Second turn: Reuses the same session (conversation continuity)
        session2, is_new2 = await service.ensure_conversation_session(
            org_id="org-test-1",
            connection=conn,
            conversation_id="conv-1001",
            agent=agent1,
            sender_name="Alice",
            force_new=False,
        )
        assert is_new2 is False
        assert session2.id == session1.id

        # 3. Third turn: Agent switched to agent2 -> creates a new session bound to agent2
        session3, is_new3 = await service.ensure_conversation_session(
            org_id="org-test-1",
            connection=conn,
            conversation_id="conv-1001",
            agent=agent2,
            sender_name="Alice",
            force_new=False,
        )
        assert is_new3 is True
        assert session3.id != session1.id
        assert session3.agent_id == "agent-2"

        # 4. User sends /reset (force_new=True) -> starts fresh session
        session4, is_new4 = await service.ensure_conversation_session(
            org_id="org-test-1",
            connection=conn,
            conversation_id="conv-1001",
            agent=agent2,
            sender_name="Alice",
            force_new=True,
        )
        assert is_new4 is True
        assert session4.id != session3.id
        assert session4.agent_id == "agent-2"

        # Verify ChannelConversation record in DB
        res = await db.execute(
            select(ChannelConversation).where(
                ChannelConversation.connection_id == "conn-1",
                ChannelConversation.conversation_id == "conv-1001",
            )
        )
        conv_record = res.scalar_one()
        assert conv_record.session_id == session4.id
        assert conv_record.agent_id == "agent-2"


@pytest.mark.asyncio
async def test_process_channel_message_with_session_and_reset(async_session_factory):
    async with async_session_factory() as db:
        org = Organization(id="org-proc", name="Proc Org", slug="proc-org")
        agent = Agent(id="agent-proc", org_id="org-proc", name="Proc Bot")
        conn = ChannelConnection(
            id="conn-proc",
            org_id="org-proc",
            provider="telegram",
            bot_token_enc="enc_token",
            bot_username="ProcTelegramBot",
            status="active",
            config={"default_agent_id": "agent-proc"},
        )
        msg1 = ChannelMessage(
            id="msg-1",
            org_id="org-proc",
            connection_id="conn-proc",
            direction="inbound",
            external_message_id="ext-1",
            conversation_id="tg-chat-999",
            sender_id="user-1",
            sender_name="Bob",
            content="Xin chào bot!",
        )
        db.add_all([org, agent, conn, msg1])
        await db.commit()

    fake_result = AgentLoopResult(
        content="Chào bạn Bob, tôi có thể giúp gì?",
        tool_calls=[],
        usage={"input_tokens": 15, "output_tokens": 20},
        latency_ms=120,
        cost_usd=0.0001,
        model="test-model",
    )

    mock_driver = AsyncMock()
    mock_driver.send_message.return_value = "ext-reply-1"

    with (
        patch("app.core.channels.jobs.SessionLocal", async_session_factory),
        patch("app.core.channels.jobs.build_channel_driver", return_value=mock_driver),
        patch("app.core.agent_loop.run_agent_loop", return_value=fake_result) as mock_loop,
    ):
        # Process message 1
        await process_channel_message({}, "org-proc", "conn-proc", "msg-1")

        # Verify run_agent_loop was called with a real session_id
        assert mock_loop.call_count == 1
        call_kwargs = mock_loop.call_args.kwargs
        session_id_turn1 = call_kwargs["session_id"]
        assert session_id_turn1 is not None

        # Verify outbound message was created with session_id
        async with async_session_factory() as db:
            res = await db.execute(
                select(ChannelMessage)
                .where(
                    ChannelMessage.connection_id == "conn-proc",
                    ChannelMessage.direction == "outbound",
                )
                .order_by(ChannelMessage.created_at.desc())
            )
            outbound = res.scalars().first()
            assert outbound is not None
            assert outbound.metadata_json["session_id"] == session_id_turn1
            assert outbound.metadata_json["model"] == "test-model"

        # Now send message 2 in the same conversation
        async with async_session_factory() as db:
            msg2 = ChannelMessage(
                id="msg-2",
                org_id="org-proc",
                connection_id="conn-proc",
                direction="inbound",
                external_message_id="ext-2",
                conversation_id="tg-chat-999",
                sender_id="user-1",
                sender_name="Bob",
                content="Câu hỏi tiếp theo...",
            )
            db.add(msg2)
            await db.commit()

        await process_channel_message({}, "org-proc", "conn-proc", "msg-2")
        assert mock_loop.call_count == 2
        call_kwargs2 = mock_loop.call_args.kwargs
        session_id_turn2 = call_kwargs2["session_id"]
        # MUST reuse the exact same session_id for multi-turn continuity!
        assert session_id_turn2 == session_id_turn1

        # Now send /reset command
        async with async_session_factory() as db:
            msg_reset = ChannelMessage(
                id="msg-3",
                org_id="org-proc",
                connection_id="conn-proc",
                direction="inbound",
                external_message_id="ext-3",
                conversation_id="tg-chat-999",
                sender_id="user-1",
                sender_name="Bob",
                content="/reset",
            )
            db.add(msg_reset)
            await db.commit()

        await process_channel_message({}, "org-proc", "conn-proc", "msg-3")
        # /reset handled directly, run_agent_loop not called for /reset
        assert mock_loop.call_count == 2

        # Verify a new session was allocated for the conversation
        async with async_session_factory() as db:
            conv = await db.scalar(
                select(ChannelConversation).where(
                    ChannelConversation.connection_id == "conn-proc",
                    ChannelConversation.conversation_id == "tg-chat-999",
                )
            )
            assert conv is not None
            assert conv.session_id != session_id_turn1
