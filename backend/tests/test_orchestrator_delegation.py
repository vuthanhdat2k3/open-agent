"""Regression suite for orchestrator-agent multi-agent delegation.

Covers the roster the orchestrator sees (_build_orchestrator_roster) and the
two ways run_agent_loop drives call_agent: sequential (one call_agent per
turn, informed by the previous result) and parallel (multiple call_agent
tool calls in a single assistant turn). Re-run this whenever agent_loop.py's
turn/tool-call handling or the orchestrator directive changes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.agent_loop import _build_orchestrator_roster, run_agent_loop
from app.db.base import Base
from app.models.agent import Agent
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.usage import UsageEvent
from app.models.user import User


def _tc(index: int, call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(index=index, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


async def _seed(session: AsyncSession) -> tuple[Organization, Agent, Agent, Agent]:
    org = Organization(name="Orchestrator Org", slug="orchestrator-org")
    session.add(org)
    await session.commit()
    await session.refresh(org)

    user = User(id="u-orch", email="orch@example.com", display_name="Orch User", is_active=True)
    provider = Provider(org_id=org.id, key="test", name="Test", base_url="http://test", api_key="sk-fake")
    session.add_all([user, provider])
    await session.commit()
    await session.refresh(provider)

    model = Model(org_id=org.id, provider_id=provider.id, name="test-model", display_name="Test Model")
    session.add(model)
    await session.commit()
    await session.refresh(model)

    orchestrator = Agent(
        org_id=org.id,
        name="Assistant",
        description="Primary user-facing agent",
        model_id=model.id,
        system_prompt="You are the primary assistant.",
        kind="orchestrator",
        tools=["call_agent"],
        allowed_risk_tiers=["safe", "read", "write", "execute", "network", "dangerous"],
        created_by_user_id="u-orch",
    )
    worker_a = Agent(
        org_id=org.id, name="Research Worker", description="Finds facts", model_id=model.id,
        system_prompt="research", kind="worker", tools=[],
    )
    worker_b = Agent(
        org_id=org.id, name="Writer Worker", description="Writes summaries", model_id=model.id,
        system_prompt="write", kind="worker", tools=[],
    )
    session.add_all([orchestrator, worker_a, worker_b])
    await session.commit()
    await session.refresh(orchestrator)
    await session.refresh(worker_a)
    await session.refresh(worker_b)
    return org, orchestrator, worker_a, worker_b


async def _make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# _build_orchestrator_roster
# ---------------------------------------------------------------------------


async def test_roster_lists_siblings_and_excludes_self() -> None:
    engine, factory = await _make_session_factory()
    async with factory() as session:
        org, orchestrator, worker_a, worker_b = await _seed(session)
        roster = await _build_orchestrator_roster(session, org.id, orchestrator.id)
        assert orchestrator.id not in roster
        assert f"{worker_a.id}: Research Worker - Finds facts" in roster
        assert f"{worker_b.id}: Writer Worker - Writes summaries" in roster
    await engine.dispose()


async def test_roster_empty_when_no_siblings() -> None:
    engine, factory = await _make_session_factory()
    async with factory() as session:
        org = Organization(name="Solo Org", slug="solo-org")
        session.add(org)
        await session.commit()
        await session.refresh(org)
        provider = Provider(org_id=org.id, key="p", name="P", base_url="http://test", api_key="sk-fake")
        session.add(provider)
        await session.commit()
        await session.refresh(provider)
        model = Model(org_id=org.id, provider_id=provider.id, name="m", display_name="M")
        session.add(model)
        await session.commit()
        await session.refresh(model)
        solo = Agent(org_id=org.id, name="Solo", model_id=model.id, system_prompt="x", kind="orchestrator")
        session.add(solo)
        await session.commit()
        await session.refresh(solo)

        roster = await _build_orchestrator_roster(session, org.id, solo.id)
        assert roster == ""
    await engine.dispose()


# ---------------------------------------------------------------------------
# Regression: run_agent_loop must include the current message even without a
# session_id - this is exactly the call shape call_agent uses for every
# delegated worker, and a prior bug silently dropped the message in that
# case (the append lived inside `if session_id:`), so every delegated worker
# saw only the system prompt and replied "your message came through empty".
# ---------------------------------------------------------------------------


async def test_run_agent_loop_includes_message_without_session_id() -> None:
    engine, factory = await _make_session_factory()
    async with factory() as session:
        org, orchestrator, worker_a, worker_b = await _seed(session)

        captured_messages: list[dict] = []

        async def mock_stream(messages, *args, **kwargs):
            captured_messages.extend(messages)
            yield {"type": "content", "text": "got it"}
            yield {"type": "usage", "usage": {"input_tokens": 1, "output_tokens": 1}, "estimated": False}

        with patch("app.core.llm.LLMClient.stream", side_effect=mock_stream):
            result = await run_agent_loop(
                agent=worker_a,
                message="find a specific fact about widgets",
                db=session,
                depth=1,
                session_id=None,
                user_id="u-orch",
            )

        assert result.content == "got it"
        user_messages = [m for m in captured_messages if m.get("role") == "user"]
        assert len(user_messages) == 1
        assert user_messages[0]["content"] == "find a specific fact about widgets"
        usage = (await session.execute(select(UsageEvent))).scalar_one()
        assert usage.created_by_user_id == "u-orch"
    await engine.dispose()


# ---------------------------------------------------------------------------
# run_agent_loop: sequential vs parallel call_agent delegation
# ---------------------------------------------------------------------------


async def test_orchestrator_sequential_delegation() -> None:
    """Turn 1 delegates to worker A, turn 2 (informed by A's result)
    delegates to worker B, turn 3 synthesizes the final answer."""
    engine, factory = await _make_session_factory()
    async with factory() as session:
        org, orchestrator, worker_a, worker_b = await _seed(session)

        delegate_calls: list[str] = []

        async def fake_delegate(agent, message, db, **kwargs):
            delegate_calls.append(agent.id)
            if agent.id == worker_a.id:
                return SimpleNamespace(content="fact: sky is blue", usage={"input_tokens": 1}, latency_ms=1)
            return SimpleNamespace(content="summary written", usage={"input_tokens": 1}, latency_ms=1)

        call_count = {"n": 0}
        captured_system_prompts: list[str] = []

        async def mock_stream(messages, *args, **kwargs):
            captured_system_prompts.append(messages[0]["content"])
            call_count["n"] += 1
            if call_count["n"] == 1:
                yield {
                    "type": "tool_calls",
                    "tool_calls": [_tc(0, "call-1", "call_agent", f'{{"target_agent_id": "{worker_a.id}", "instruction": "find a fact"}}')],
                }
            elif call_count["n"] == 2:
                yield {
                    "type": "tool_calls",
                    "tool_calls": [_tc(0, "call-2", "call_agent", f'{{"target_agent_id": "{worker_b.id}", "instruction": "write it up"}}')],
                }
            else:
                yield {"type": "content", "text": "Done: fact is blue, summarized."}
            yield {"type": "usage", "usage": {"input_tokens": 5, "output_tokens": 5}, "estimated": False}

        with (
            patch("app.core.llm.LLMClient.stream", side_effect=mock_stream),
            patch("app.core.agent_loop.run_agent_loop", side_effect=fake_delegate) as patched_run,
        ):
            # `run_agent_loop` under test is the real function captured above
            # (imported before patching); the patch only affects the
            # recursive lookup inside the call_agent tool.
            result = await run_agent_loop(
                agent=orchestrator, message="Research and summarize", db=session, user_id="u-orch",
            )

        assert result.content == "Done: fact is blue, summarized."
        assert delegate_calls == [worker_a.id, worker_b.id]
        assert call_count["n"] == 3
        assert worker_a.id in captured_system_prompts[0]
        assert worker_b.id in captured_system_prompts[0]
        assert patched_run.call_count == 2
    await engine.dispose()


async def test_orchestrator_parallel_delegation() -> None:
    """A single assistant turn emits two call_agent tool calls at once;
    both must be executed before the orchestrator's final turn."""
    engine, factory = await _make_session_factory()
    async with factory() as session:
        org, orchestrator, worker_a, worker_b = await _seed(session)

        delegate_calls: list[str] = []

        async def fake_delegate(agent, message, db, **kwargs):
            delegate_calls.append(agent.id)
            return SimpleNamespace(content=f"result from {agent.name}", usage={"input_tokens": 1}, latency_ms=1)

        call_count = {"n": 0}

        async def mock_stream(messages, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                yield {
                    "type": "tool_calls",
                    "tool_calls": [
                        _tc(0, "call-a", "call_agent", f'{{"target_agent_id": "{worker_a.id}", "instruction": "task A"}}'),
                        _tc(1, "call-b", "call_agent", f'{{"target_agent_id": "{worker_b.id}", "instruction": "task B"}}'),
                    ],
                }
            else:
                yield {"type": "content", "text": "Both done."}
            yield {"type": "usage", "usage": {"input_tokens": 5, "output_tokens": 5}, "estimated": False}

        with (
            patch("app.core.llm.LLMClient.stream", side_effect=mock_stream),
            patch("app.core.agent_loop.run_agent_loop", side_effect=fake_delegate) as patched_run,
        ):
            result = await run_agent_loop(
                agent=orchestrator, message="Do A and B in parallel", db=session, user_id="u-orch",
            )

        # Both delegated calls happened within a single orchestrator turn
        # (call_count reached 2 total: the delegating turn + the final
        # content-only turn), not one per delegate like the sequential case.
        assert result.content == "Both done."
        assert set(delegate_calls) == {worker_a.id, worker_b.id}
        assert call_count["n"] == 2
        assert patched_run.call_count == 2
    await engine.dispose()
