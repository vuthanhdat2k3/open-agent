"""Regression suite for orchestrator-agent multi-agent delegation.

Covers the roster the orchestrator sees (_build_orchestrator_roster) and the
two ways run_agent_loop drives call_agent: sequential (one call_agent per
turn, informed by the previous result) and parallel (multiple call_agent
tool calls in a single assistant turn). Re-run this whenever agent_loop.py's
turn/tool-call handling or the orchestrator directive changes.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.agent_loop import (
    _build_orchestrator_roster,
    _infer_capabilities,
    _recent_delegate_agent_id,
    _route_google_worker_tool,
    _route_orchestrator_turn,
    run_agent_loop,
)
from app.core.tools.types import ToolSpec
from app.db.base import Base, utc_now
from app.models.agent import Agent
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.task import Task
from app.models.usage import UsageEvent
from app.models.user import User


def _tc(index: int, call_id: str, name: str, arguments: str) -> dict:
    return {"index": index, "id": call_id, "name": name, "arguments": arguments}


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


def test_infer_capabilities_uses_tool_prefix_and_agent_name() -> None:
    agent = Agent(name="Email Intelligence", tools=["email_send", "email_search", "memory_recall"])
    assert _infer_capabilities(agent) == {"email", "memory", "email intelligence"}


def test_ambiguous_or_unmatched_route_keeps_auto_tool_choice() -> None:
    a = Agent(id="a", name="email-intelligence", tools=["email_send"])
    b = Agent(id="b", name="calendar-intelligence", tools=["calendar_create_event"])
    choice, directive = _route_orchestrator_turn(
        "Help me with something", [], {"email": [a], "calendar": [b]}, {}
    )
    assert choice == "auto"
    assert directive is None


def test_google_worker_routes_clear_english_and_vietnamese_intents() -> None:
    cases = (
        ("remove label from email", "email_remove_label"),
        ("gắn nhãn cho mail", "email_apply_label"),
        ("list labels in Gmail", "email_list_labels"),
        ("mark unread email", "email_mark_unread"),
        ("đánh dấu đã đọc mail", "email_mark_read"),
        ("unstar email", "email_unstar"),
        ("gắn sao email", "email_star"),
        ("archive mail", "email_archive"),
        ("khôi phục email", "email_restore"),
        ("xóa mail", "email_trash"),
        ("reply to email", "email_reply"),
        ("chuyển tiếp mail", "email_forward"),
        ("send draft email", "email_send"),
        ("compose email to alice@example.com", "email_create_draft"),
        ("read email id abc", "email_get"),
        ("tìm các mail trong hôm nay", "email_search"),
        ("list new email in inbox", "email_list_new"),
        ("find the quarterly plan in Drive", "drive_list_files"),
        ("read Drive file id abc", "drive_get_file"),
        ("tạo file mới trên Drive", "drive_create_file"),
        ("update Drive file id abc", "drive_update_file"),
        ("xóa file này trên Drive", "drive_delete_file"),
        ("show my calendar events today", "calendar_list_events"),
        ("read calendar event id abc", "calendar_get_event"),
        ("đặt lịch họp ngày mai", "calendar_create_event"),
        ("reschedule calendar event id abc", "calendar_update_event"),
        ("hủy sự kiện lịch", "calendar_delete_event"),
    )
    names = {expected for _, expected in cases}
    tools = {
        name: ToolSpec(name=name, description=name, input_schema={}, run=None)
        for name in names
    }
    for message, expected in cases:
        assert _route_google_worker_tool(message, tools) == {
            "type": "function",
            "function": {"name": expected},
        }


def test_google_worker_keeps_auto_for_ambiguity_or_missing_tool() -> None:
    email_search = ToolSpec(
        name="email_search", description="email", input_schema={}, run=None
    )
    drive_list = ToolSpec(
        name="drive_list_files", description="drive", input_schema={}, run=None
    )
    assert _route_google_worker_tool("hello", {email_search.name: email_search}) == "auto"
    assert _route_google_worker_tool(
        "find mail and Drive files",
        {email_search.name: email_search, drive_list.name: drive_list},
    ) == "auto"
    calendar_create = ToolSpec(
        name="calendar_create_event", description="calendar", input_schema={}, run=None
    )
    calendar_delete = ToolSpec(
        name="calendar_delete_event", description="calendar", input_schema={}, run=None
    )
    assert _route_google_worker_tool(
        "create and delete a calendar event",
        {
            calendar_create.name: calendar_create,
            calendar_delete.name: calendar_delete,
        },
    ) == "auto"
    assert _route_google_worker_tool("find mail", {}) == "auto"


def test_sticky_route_for_short_followup() -> None:
    email = Agent(id="email", name="email-intelligence", tools=["email_send"])
    spec = ToolSpec(name="delegate_to_email", description="email", input_schema={}, run=None)
    choice, directive = _route_orchestrator_turn(
        "hãy gửi", [], {"email": [email]}, {"email": spec}, "email"
    )
    assert choice == {"type": "function", "function": {"name": "delegate_to_email"}}
    assert directive and "short follow-up" in directive


def test_sticky_route_does_not_hijack_long_message_or_tier1() -> None:
    email = Agent(id="email", name="email-intelligence", tools=["email_send"])
    calendar = Agent(id="calendar", name="calendar-intelligence", tools=["calendar_create_event"])
    email_spec = ToolSpec(name="delegate_to_email", description="email", input_schema={}, run=None)
    calendar_spec = ToolSpec(name="delegate_to_calendar", description="calendar", input_schema={}, run=None)
    choice, _ = _route_orchestrator_turn(
        "please send this very long request with many details and no capability keyword",
        [], {"email": [email]}, {"email": email_spec}, "email"
    )
    assert choice == "auto"
    choice, _ = _route_orchestrator_turn(
        "schedule a meeting", [], {"email": [email], "calendar": [calendar]},
        {"email": email_spec, "calendar": calendar_spec}, "email"
    )
    assert choice == {"type": "function", "function": {"name": "delegate_to_calendar"}}


async def test_recent_delegate_agent_id_is_fresh_and_unambiguous() -> None:
    engine, factory = await _make_session_factory()
    async with factory() as session:
        org, orchestrator, _, _ = await _seed(session)
        email = Agent(org_id=org.id, name="email-intelligence", kind="worker")
        calendar = Agent(org_id=org.id, name="calendar-intelligence", kind="worker")
        session.add_all([email, calendar])
        await session.commit()
        session.add(Task(org_id=org.id, root_run_id="root", agent_id=email.id, started_at=utc_now()))
        await session.commit()
        assert await _recent_delegate_agent_id(session, org.id, "root", orchestrator.id) == email.id
        session.add(Task(org_id=org.id, root_run_id="root", agent_id=calendar.id, started_at=utc_now()))
        await session.commit()
        assert await _recent_delegate_agent_id(session, org.id, "root", orchestrator.id) is None
        session.add(Task(org_id=org.id, root_run_id="old", agent_id=email.id,
                         started_at=utc_now() - timedelta(minutes=31)))
        await session.commit()
        assert await _recent_delegate_agent_id(session, org.id, "old", orchestrator.id) is None
        session.add(Task(
            org_id=org.id,
            root_run_id="previous-turn",
            agent_id=email.id,
            started_at=utc_now(),
            progress={"session_id": "chat-session"},
        ))
        await session.commit()
        assert (
            await _recent_delegate_agent_id(
                session, org.id, "new-turn", orchestrator.id, "chat-session"
            )
            == email.id
        )
    await engine.dispose()


async def test_orchestrator_forces_named_email_delegate() -> None:
    engine, factory = await _make_session_factory()
    async with factory() as session:
        org, orchestrator, _, _ = await _seed(session)
        email_agent = Agent(
            org_id=org.id,
            name="email-intelligence",
            description="Handles Gmail actions",
            model_id=orchestrator.model_id,
            system_prompt="email worker",
            kind="worker",
            tools=["email_send"],
        )
        session.add(email_agent)
        await session.commit()
        await session.refresh(email_agent)

        captured_choices: list[object] = []
        call_count = {"n": 0}

        async def fake_delegate(agent, message, db, **kwargs):
            return SimpleNamespace(content="approval requested", usage={"input_tokens": 1}, latency_ms=1)

        async def mock_stream(messages, *args, **kwargs):
            captured_choices.append(kwargs.get("tool_choice"))
            call_count["n"] += 1
            if call_count["n"] == 1:
                yield {
                    "type": "tool_calls",
                    "tool_calls": [
                        _tc(
                            0,
                            "call-email",
                            "delegate_to_email_intelligence",
                            '{"instruction":"send a greeting email"}',
                        )
                    ],
                }
            else:
                yield {"type": "content", "text": "Delegated."}
            yield {"type": "usage", "usage": {"input_tokens": 1, "output_tokens": 1}, "estimated": False}

        with (
            patch("app.core.llm.LLMClient.stream", side_effect=mock_stream),
            patch("app.core.agent_loop.run_agent_loop", side_effect=fake_delegate),
        ):
            result = await run_agent_loop(
                agent=orchestrator,
                message="Gửi email chào đến dat@example.com",
                db=session,
                user_id="u-orch",
            )

        assert result.content == "Delegated."
        assert captured_choices[0] == {
            "type": "function",
            "function": {"name": "delegate_to_email_intelligence"},
        }
        assert captured_choices[1] == "auto"
    await engine.dispose()


async def test_worker_forces_google_tool_only_on_first_iteration() -> None:
    engine, factory = await _make_session_factory()
    async with factory() as session:
        _, _, worker, _ = await _seed(session)
        worker.tools = ["email_search"]
        worker.allowed_risk_tiers = ["safe", "read"]
        await session.commit()

        captured_choices: list[object] = []
        captured_system_prompts: list[str] = []
        call_count = 0

        async def mock_stream(messages, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_choices.append(kwargs.get("tool_choice"))
            captured_system_prompts.append(messages[0]["content"])
            if call_count == 1:
                yield {
                    "type": "tool_calls",
                    "tool_calls": [
                        _tc(
                            0,
                            "call-email-search",
                            "email_search",
                            '{"query":"newer_than:1d"}',
                        )
                    ],
                }
            else:
                yield {"type": "content", "text": "No matching email."}
            yield {
                "type": "usage",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "estimated": False,
            }

        async def fake_execute(spec, args, ctx):
            return "No matching email"

        with (
            patch("app.core.llm.LLMClient.stream", side_effect=mock_stream),
            patch("app.core.agent_loop.execute_tool_call", side_effect=fake_execute),
        ):
            result = await run_agent_loop(
                agent=worker,
                message="tìm các mail trong hôm nay",
                db=session,
                user_id="u-orch",
            )

        assert result.content == "No matching email."
        assert captured_choices == [
            {"type": "function", "function": {"name": "email_search"}},
            "auto",
        ]
        assert "Connected-data tool behavior" in captured_system_prompts[0]
        assert "Current UTC time:" in captured_system_prompts[0]
        assert "today's UTC range is after:" in captured_system_prompts[0]
        assert "Do not fetch every item individually" in captured_system_prompts[0]
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
                user_role="user",
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
                user_role="user",
            )

        # Both delegated calls happened within a single orchestrator turn
        # (call_count reached 2 total: the delegating turn + the final
        # content-only turn), not one per delegate like the sequential case.
        assert result.content == "Both done."
        assert set(delegate_calls) == {worker_a.id, worker_b.id}
        assert call_count["n"] == 2
        assert patched_run.call_count == 2
    await engine.dispose()
