"""End-to-end coverage for chat stream recovery (no Docker / no real LLM).

Drives the *real* agent loop (with a faked `LLMClient.stream`) so the new
durable event log is actually written, then exercises the recovery HTTP
surface — `GET /api/chat/runs/{id}` (status + progress) and
`GET /api/chat/runs/{id}/events` (drain snapshot + live follow) — and
asserts the in-flight frames (reasoning, token, tool_call, tool_result,
message_done) are recoverable.

Mirrors the proven fixture pattern in ``test_a2a_server.py`` (in-memory
engine + dependency overrides + patched LLM stream).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.routes import chat as chat_route_mod
from app.core import chat_events as chat_events_mod
from app.core.quota.dependencies import _redis_client
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolSpec
from app.db.base import Base
from app.db.session import get_db
from app.dependencies import get_current_org_id, get_current_user
from app.main import app
from app.models.agent import Agent
from app.models.membership import Membership
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def test_user():
    return User(id="user-chat", email="chat@example.com", display_name="Chat User", is_active=True)


@pytest.fixture
def client(async_session_factory, test_user):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    async def _override_redis():
        yield None

    async def _override_user():
        return test_user

    async def _override_org():
        return "org-chat"

    # The event recorder writes through SessionLocal; point it at the same
    # in-memory engine the request sessions use so events land in the test DB.
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_redis_client] = _override_redis
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_org_id] = _override_org
    with (
        patch.object(chat_events_mod, "SessionLocal", async_session_factory),
        patch.object(chat_route_mod, "SessionLocal", async_session_factory),
        TestClient(app) as test_client,
    ):
        yield test_client
    app.dependency_overrides.clear()


def _fake_llm_stream():
    """Emit reasoning → content → one tool call (first iteration only) → more
    content → usage. The loop calls the stream per iteration, so the single
    tool call forces a second iteration (tool result fed back in) and exercises
    both the token and tool_call/tool_result recovery paths before finishing.
    """

    calls = {"n": 0}

    async def mock_stream(*args, **kwargs):
        calls["n"] += 1
        yield {"type": "reasoning", "text": "let me think… "}
        yield {"type": "content", "text": "Hello "}
        if calls["n"] == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [{"index": 0, "id": "tc-1", "name": "test_echo", "arguments": '{"x":"1"}'}],
            }
        yield {"type": "content", "text": "after tool "}
        yield {
            "type": "usage",
            "usage": {"input_tokens": 12, "output_tokens": 9},
            "estimated": False,
        }

    return mock_stream


@pytest.mark.asyncio
async def test_chat_stream_recovery_e2e(client, async_session_factory, test_user):
    from app.core.tools.registry import register

    async def _echo_tool(args, ctx):
        return f"echo:{args}"

    register(
        ToolSpec(
            name="test_echo",
            description="Echo tool for recovery E2E",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            run=_echo_tool,
            risk_tier=RiskTier.safe,
        )
    )

    async with async_session_factory() as db:
        mem = Membership(org_id="org-chat", user_id="user-chat", role="operator")
        prov = Provider(
            id="p-chat", org_id="org-chat", key="t", name="t", base_url="http://test", api_key="sk-fake"
        )
        mdl = Model(id="m-chat", org_id="org-chat", provider_id="p-chat", name="t", display_name="t")
        agent = Agent(
            id="agent-chat-1",
            org_id="org-chat",
            name="Recovery Agent",
            model_id="m-chat",
            tools=["test_echo"],
            allowed_risk_tiers=["safe"],
        )
        db.add_all([mem, prov, mdl, agent])
        await db.commit()

        # Run the real agent loop (records events via patched SessionLocal
        # set up by the client fixture).
        with patch("app.core.llm.LLMClient.stream", side_effect=_fake_llm_stream()):
            result = await ChatService(db).run(
                "org-chat",
                ChatRequest(agent_id="agent-chat-1", message="hi", stream=False),
                user_id="user-chat",
                root_run_id="run-e2e-1",
            )
    assert result.error is None
    assert "Hello" in result.content

    # --- GET /runs/{id}: status + live progress checkpoint ---
    run_resp = client.get("/api/chat/runs/run-e2e-1")
    assert run_resp.status_code == 200, run_resp.text
    run_json = run_resp.json()
    assert run_json["status"] == "succeeded"
    assert run_json["progress"]["phase"] == "done"
    assert run_json["progress"]["last_seq"] >= 1

    # --- GET /runs/{id}/events?follow=false: drain snapshot ---
    snap = client.get("/api/chat/runs/run-e2e-1/events?follow=false")
    assert snap.status_code == 200, snap.text
    events = snap.json()["events"]
    names = [e["event"] for e in events]
    for expected in ("message_start", "reasoning", "token", "tool_call", "tool_result", "message_done"):
        assert expected in names, f"missing {expected} in {names}"
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs), "events must be monotonic per run"
    # Replay is idempotent: a client rebuilds the exact same frames.
    assert sum(1 for e in events if e["event"] == "token") >= 2

    # --- GET /runs/{id}/events?follow=true: live follow drains + closes ---
    follow = client.get("/api/chat/runs/run-e2e-1/events?follow=true")
    assert follow.status_code == 200
    assert "event: message_done" in follow.text
    assert "event: error" not in follow.text

    # --- Durable transcript: final assistant message persisted to session ---
    async with async_session_factory() as db:
        msgs = list(
            (await db.execute(select(Message).where(Message.role == "assistant"))).scalars().all()
        )
    assert any("Hello" in m.content for m in msgs)


@pytest.mark.asyncio
async def test_empty_finalization_retries_without_tools_or_duplicate_execution(
    async_session_factory,
):
    from app.core.tools.registry import register

    execution_count = 0

    async def _once_tool(args, ctx):
        nonlocal execution_count
        execution_count += 1
        return "No emails found."

    register(
        ToolSpec(
            name="finalization_once_tool",
            description="Tool for finalization retry regression",
            input_schema={"type": "object", "properties": {}},
            run=_once_tool,
            risk_tier=RiskTier.safe,
        )
    )

    calls: list[dict] = []

    async def _empty_then_final(
        self, messages, tools=None, temperature=0.7, tool_choice=None, thinking=None
    ):
        calls.append({"tools": tools, "tool_choice": tool_choice})
        if len(calls) == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "finalization-call-1",
                        "name": "finalization_once_tool",
                        "arguments": "{}",
                    }
                ],
            }
        elif len(calls) == 2:
            yield {
                "type": "usage",
                "usage": {"input_tokens": 10, "output_tokens": 0},
                "estimated": False,
            }
        else:
            yield {"type": "content", "text": "Final answer after retry."}
            yield {
                "type": "usage",
                "usage": {"input_tokens": 11, "output_tokens": 5},
                "estimated": False,
            }

    async with async_session_factory() as db:
        prov = Provider(
            id="p-finalization", org_id="org-chat", key="finalization", name="finalization", base_url="http://test", api_key="sk-test"
        )
        mdl = Model(
            id="m-finalization", org_id="org-chat", provider_id=prov.id,
            name="finalization-model", display_name="finalization-model"
        )
        agent = Agent(
            id="agent-finalization", org_id="org-chat", name="Finalization Agent",
            model_id=mdl.id, tools=["finalization_once_tool"], allowed_risk_tiers=["safe"]
        )
        db.add_all([prov, mdl, agent])
        await db.commit()

        with patch("app.core.llm.LLMClient.stream", new=_empty_then_final):
            result = await ChatService(db).run(
                "org-chat",
                ChatRequest(agent_id=agent.id, message="find emails", stream=False),
                root_run_id="run-finalization-retry",
            )

    assert result.error is None
    assert result.content == "Final answer after retry."
    assert execution_count == 1
    assert len(calls) == 3
    assert calls[0]["tools"]
    assert calls[1]["tools"]
    assert calls[2]["tools"] is None
    assert calls[2]["tool_choice"] is None
    assert result.usage == {"input_tokens": 21, "output_tokens": 5, "estimated": False}
