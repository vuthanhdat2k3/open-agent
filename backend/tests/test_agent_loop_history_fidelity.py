"""Integration test: second turn sees the full first-turn tool history."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core import session_log as slog
from app.core.agent_loop import run_agent_loop
from app.core.session_surface import derive_messages
from app.db.base import Base
from app.models.agent import Agent
from app.models.model import Model
from app.models.provider import Provider
from app.models.session import Session
from app.models.user import User


@pytest.fixture
async def db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_second_turn_sees_full_tool_history(db_factory):
    """Turn 2's provider request should include the tool_call and tool_result
    from turn 1 - the fidelity problem that motivated the event log."""
    async with db_factory() as db:
        db.add(User(id="u-hf", email="hf@example.com", display_name="HF", is_active=True))
        db.add(
            Provider(
                id="p-hf",
                org_id="org-hf",
                key="p-key",
                name="p-name",
                base_url="http://t",
                api_key="sk-fake",
            )
        )
        db.add(
            Model(
                id="m-hf",
                org_id="org-hf",
                provider_id="p-hf",
                name="m-name",
                display_name="m-name",
            )
        )
        db.add(
            Agent(
                id="agent-hf",
                org_id="org-hf",
                name="HF",
                model_id="m-hf",
                created_by_user_id="u-hf",
            )
        )
        db.add(
            Session(
                id="s-hf",
                org_id="org-hf",
                agent_id="agent-hf",
                created_by_user_id="u-hf",
                title="HF",
            )
        )
        await db.commit()

    captured_turn2: list[dict[str, Any]] = []

    async def fake_stream(messages, *args, **kwargs):
        # Capture only the second-turn request.
        # We detect "second turn" by looking for a role:tool message in the
        # caller-provided history (only the second call should have it).
        if any(m.get("role") == "tool" for m in messages):
            captured_turn2.extend(messages)
            yield {"type": "content", "text": "second turn answer"}
            yield {
                "type": "usage",
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "estimated": False,
            }
        else:
            # First turn: emit a tool call, then a final answer.
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "tc-hf-1",
                        "name": "echo",
                        "arguments": json.dumps({"text": "ping"}),
                    }
                ],
            }
            yield {"type": "content", "text": "I have run echo"}
            yield {
                "type": "usage",
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "estimated": False,
            }

    async def fake_complete(*args, **kwargs):
        return ("summary", 10, 0.001)

    async with db_factory() as db:
        agent = await db.get(Agent, "agent-hf")
        with (
            patch("app.core.llm.LLMClient.stream", side_effect=fake_stream),
            patch("app.core.memory.tiers.LLMClient.complete", side_effect=fake_complete),
        ):
            await run_agent_loop(
                agent=agent,
                message="please run echo",
                db=db,
                session_id="s-hf",
                user_id="u-hf",
            )
        events = await slog.load_events(db, "s-hf")
        assert [(event.type, event.data.get("tool_call_id")) for event in events] == [
            (slog.USER_MESSAGE, None),
            (slog.TOOL_CALL, "tc-hf-1"),
            (slog.TOOL_RESULT, "tc-hf-1"),
            (slog.ASSISTANT_MESSAGE, None),
        ]

    # Run a second turn and capture its history.
    async with db_factory() as db:
        agent = await db.get(Agent, "agent-hf")
        with (
            patch("app.core.llm.LLMClient.stream", side_effect=fake_stream),
            patch("app.core.memory.tiers.LLMClient.complete", side_effect=fake_complete),
        ):
            await run_agent_loop(
                agent=agent,
                message="now what did you do?",
                db=db,
                session_id="s-hf",
                user_id="u-hf",
            )

    assert captured_turn2, "second-turn stream was not invoked"
    roles = [m.get("role") for m in captured_turn2]
    # Old code: tool_calls/result lost across turns; the second turn only saw
    # a flat assistant text. Event log: turn 2 sees the tool role.
    assert "tool" in roles, f"tool history lost across turns: got roles={roles}"
    assistant_messages = [m for m in captured_turn2 if m.get("role") == "assistant"]
    assert assistant_messages[-1].get("tool_calls") is None
    # The first user/assistant/tool/result turn should appear before
    # turn 2's user message.
    tool_idx = roles.index("tool")
    user_idx = roles.index("user", tool_idx)
    assert tool_idx < user_idx


@pytest.mark.asyncio
async def test_session_event_log_round_trip_via_derive_messages(db_factory):
    """Events appended by the agent loop are folded back into the same wire
    format that providers expect."""
    async with db_factory() as db:
        # Build a small log by hand to exercise surface projection.
        await slog.append_event(
            db,
            session_id="s-rt",
            org_id="o",
            type_=slog.USER_MESSAGE,
            data={"content": "what is the time?"},
        )
        await slog.append_event(
            db,
            session_id="s-rt",
            org_id="o",
            type_=slog.ASSISTANT_MESSAGE,
            data={"content": None, "tool_calls": []},
        )
        await slog.append_event(
            db,
            session_id="s-rt",
            org_id="o",
            type_=slog.TOOL_CALL,
            data={
                "tool_call_id": "tc-rt-1",
                "name": "now",
                "arguments": "{}",
            },
        )
        await slog.append_event(
            db,
            session_id="s-rt",
            org_id="o",
            type_=slog.TOOL_RESULT,
            data={"tool_call_id": "tc-rt-1", "content": "12:00"},
        )
        await slog.append_event(
            db,
            session_id="s-rt",
            org_id="o",
            type_=slog.ASSISTANT_MESSAGE,
            data={"content": "It is 12:00"},
        )
        await db.commit()

        events = await slog.load_events(db, "s-rt")
        msgs = derive_messages(events)
        assert msgs[0] == {"role": "user", "content": "what is the time?"}
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["tool_calls"][0]["function"]["name"] == "now"
        assert msgs[2] == {"role": "tool", "tool_call_id": "tc-rt-1", "content": "12:00"}
        assert msgs[3] == {"role": "assistant", "content": "It is 12:00"}
