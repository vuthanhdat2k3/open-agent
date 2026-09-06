"""Tests verifying that subagent executions (depth > 0) never leak messages into parent chat sessions."""

from __future__ import annotations

from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.agent_loop import run_agent_loop, await_deferred_user_write
from app.core import session_log as slog
from app.db.base import Base
from app.models.agent import Agent
from app.models.message import Message
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.session import Session
from app.models.user import User


async def _make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed(db: AsyncSession):
    org = Organization(name="Test Org", slug="test-org")
    db.add(org)
    await db.commit()
    await db.refresh(org)

    user = User(id="u-1", email="user@example.com", display_name="User", is_active=True)
    provider = Provider(org_id=org.id, key="test", name="Test Provider", base_url="http://test", api_key="sk-fake")
    db.add_all([user, provider])
    await db.commit()
    await db.refresh(provider)

    model = Model(org_id=org.id, provider_id=provider.id, name="qwen3.8-flash", display_name="Qwen 3.8 Flash", active=True)
    db.add(model)
    await db.commit()
    await db.refresh(model)

    agent = Agent(
        org_id=org.id,
        name="Worker Agent",
        model_id=model.id,
        system_prompt="You are a worker.",
        tools=[],
    )
    chat_session = Session(
        id="s-isolation-test",
        org_id=org.id,
        agent_id=agent.id,
        created_by_user_id=user.id,
        title="Test Session",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    chat_session.agent_id = agent.id
    db.add(chat_session)
    await db.commit()
    await db.refresh(chat_session)
    return org, agent, model, chat_session


async def test_subagent_does_not_leak_messages_into_parent_session():
    engine, factory = await _make_session_factory()
    async with factory() as db:
        org, agent, model, chat_session = await _seed(db)

        async def mock_stream(messages, *args, **kwargs):
            yield {"type": "content", "text": "subagent completed task"}
            yield {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 5}, "estimated": False}

        with patch("app.core.llm.LLMClient.stream", side_effect=mock_stream):
            # Subagent run with depth=1
            result = await run_agent_loop(
                agent=agent,
                message="internal instruction to subagent",
                db=db,
                depth=1,
                session_id=chat_session.id,
                user_id="u-1",
            )

        assert result.content == "subagent completed task"
        await await_deferred_user_write(None)

        # Verify NO messages in Message table
        msgs = (await db.execute(select(Message).where(Message.session_id == chat_session.id))).scalars().all()
        assert len(msgs) == 0, f"Expected 0 messages in session, found {len(msgs)}: {[m.content for m in msgs]}"

        # Verify NO events in session_events
        events = await slog.load_events(db, chat_session.id)
        assert len(events) == 0, f"Expected 0 events in session_events, found {len(events)}"

    await engine.dispose()


async def test_root_agent_persists_messages_into_session():
    engine, factory = await _make_session_factory()
    async with factory() as db:
        org, agent, model, chat_session = await _seed(db)

        async def mock_stream(messages, *args, **kwargs):
            yield {"type": "content", "text": "root agent reply"}
            yield {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 5}, "estimated": False}

        with patch("app.core.llm.LLMClient.stream", side_effect=mock_stream):
            # Root agent run with depth=0
            result = await run_agent_loop(
                agent=agent,
                message="hello from user",
                db=db,
                depth=0,
                session_id=chat_session.id,
                user_id="u-1",
            )

        assert result.content == "root agent reply"

        # Verify messages in Message table
        msgs = (await db.execute(select(Message).where(Message.session_id == chat_session.id))).scalars().all()
        roles = [m.role for m in msgs]
        assert "user" in roles
        assert "assistant" in roles

        # Verify events in session_events
        events = await slog.load_events(db, chat_session.id)
        event_types = [e.type for e in events]
        assert slog.USER_MESSAGE in event_types
        assert slog.ASSISTANT_MESSAGE in event_types

    await engine.dispose()


async def test_workflow_agent_node_resolves_model_name_to_id():
    from app.core.workflow.engine import _run_agent_node

    engine, factory = await _make_session_factory()
    async with factory() as db:
        org, agent, model, chat_session = await _seed(db)

        captured_model_id: dict[str, str] = {}

        async def fake_run_agent_loop(agent, text, db, **kwargs):
            captured_model_id["model_id"] = kwargs.get("model_id")

            class _Res:
                content = "filtered output"
                error = None

            return _Res()

        with patch("app.core.agent_loop.run_agent_loop", fake_run_agent_loop):
            node = {
                "id": "filter_agent",
                "kind": "agent",
                "label": "Filter Agent",
                "_org_id": org.id,
                "agent_id": agent.id,
                "model_id": "qwen3.8-flash",  # passed by model name!
                "parameters": {"mode": "inherit"},
            }
            res = await _run_agent_node(
                node,
                node.get("parameters") or {},
                node_run=None,
                upstream_text="input data",
                db=db,
                actor_user_id=None,
                actor_user_role=None,
            )

            assert captured_model_id["model_id"] == model.id
            assert res.text == "filtered output"

    await engine.dispose()
