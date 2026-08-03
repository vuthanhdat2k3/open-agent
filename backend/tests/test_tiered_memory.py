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


@pytest.mark.asyncio
async def test_compact_tiered_memory_exceeding_hot_window(async_session_factory):
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import select

    from app.models.memory import SessionMemory
    from app.models.organization import Organization
    from app.models.session import Session

    async with async_session_factory() as db:
        org = Organization(id="org-warm", name="Warm Org", slug="warm-org")
        sess = Session(id="s-warm", org_id="org-warm", agent_id="agent-1", title="Test Session")
        db.add_all([org, sess])

        for i in range(1, 7):
            db.add(
                Message(
                    org_id="org-warm",
                    session_id="s-warm",
                    role="user" if i % 2 != 0 else "assistant",
                    content=f"Message {i}",
                    position=i,
                )
            )
        await db.commit()

        mock_model = Model(id="m-1", name="dummy-model", provider_id="p-1")
        mock_provider = Provider(id="p-1", key="dummy-key", name="dummy", base_url="http://dummy", api_key="sk-fake")

        with patch("app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = ("Summarized warm transcript", 10, 0.001)

            res = await compact_tiered_memory(
                session_id="s-warm",
                db=db,
                agent_model=mock_model,
                provider=mock_provider,
                hot_window=2,
                org_id="org-warm",
            )

            assert "Message 5" in res["hot"]
            assert "Message 6" in res["hot"]
            assert "Message 1" not in res["hot"]
            assert res["warm"] == "Summarized warm transcript"

            # Assert SessionMemory persistence and valid org_id
            smem_res = await db.execute(
                select(SessionMemory).where(
                    SessionMemory.session_id == "s-warm",
                    SessionMemory.key == "warm_summary",
                )
            )
            smem = smem_res.scalar_one_or_none()
            assert smem is not None
            assert smem.org_id == "org-warm"
            assert smem.value == "Summarized warm transcript"


@pytest.mark.asyncio
async def test_compact_tiered_memory_updates_existing_warm_summary(async_session_factory):
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import select

    from app.models.memory import SessionMemory

    async with async_session_factory() as db:
        existing_smem = SessionMemory(
            id="smem-1",
            org_id="org-exist",
            session_id="s-exist",
            key="warm_summary",
            value="Old summary",
        )
        db.add(existing_smem)
        for i in range(1, 5):
            db.add(
                Message(
                    org_id="org-exist",
                    session_id="s-exist",
                    role="user",
                    content=f"Exist msg {i}",
                    position=i,
                )
            )
        await db.commit()

        mock_model = Model(name="dummy-model", provider_id="p-1")
        mock_provider = Provider(id="p-1", key="dummy-key", name="dummy", base_url="http://dummy", api_key="sk-fake")

        with patch("app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = ("Updated warm summary", 15, 0.002)

            res = await compact_tiered_memory(
                session_id="s-exist",
                db=db,
                agent_model=mock_model,
                provider=mock_provider,
                hot_window=2,
                org_id="org-exist",
            )

            assert res["warm"] == "Updated warm summary"

            smem_res = await db.execute(
                select(SessionMemory).where(
                    SessionMemory.session_id == "s-exist",
                    SessionMemory.key == "warm_summary",
                )
            )
            smem = smem_res.scalar_one_or_none()
            assert smem.value == "Updated warm summary"


@pytest.mark.asyncio
async def test_compact_tiered_memory_with_cold_facts(async_session_factory):
    from unittest.mock import AsyncMock, patch

    from app.models.memory import AgentMemory

    async with async_session_factory() as db:
        mem1 = AgentMemory(
            id="mem-low",
            org_id="org-cold",
            agent_id="agent-cold",
            memory_type="user",
            attribute="location",
            value="Hanoi",
            importance=2,
        )
        mem2 = AgentMemory(
            id="mem-high",
            org_id="org-cold",
            agent_id="agent-cold",
            memory_type="user",
            attribute="role",
            value="Lead Engineer",
            importance=10,
        )
        db.add_all([mem1, mem2])

        for i in range(1, 5):
            db.add(
                Message(
                    org_id="org-cold",
                    session_id="s-cold",
                    role="user",
                    content=f"Cold msg {i}",
                    position=i,
                )
            )
        await db.commit()

        mock_model = Model(name="dummy-model", provider_id="p-1")
        mock_provider = Provider(id="p-1", key="dummy-key", name="dummy", base_url="http://dummy", api_key="sk-fake")

        with patch("app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = ("Warm summary", 5, 0.001)

            res = await compact_tiered_memory(
                session_id="s-cold",
                db=db,
                agent_model=mock_model,
                provider=mock_provider,
                hot_window=2,
                agent_id="agent-cold",
                org_id="org-cold",
            )

            assert "user.role: Lead Engineer" in res["cold"]
            assert "user.location: Hanoi" in res["cold"]
            # Assert importance ordering (Lead Engineer before Hanoi)
            assert res["cold"].index("user.role: Lead Engineer") < res["cold"].index("user.location: Hanoi")
            assert "[Cold Memory / User Profile]" in res["combined"]


@pytest.mark.asyncio
async def test_compact_tiered_memory_llm_fallback(async_session_factory):
    from unittest.mock import AsyncMock, patch

    async with async_session_factory() as db:
        for i in range(1, 5):
            db.add(
                Message(
                    org_id="org-fall",
                    session_id="s-fall",
                    role="user",
                    content=f"Fallback msg {i}",
                    position=i,
                )
            )
        await db.commit()

        mock_model = Model(name="dummy-model", provider_id="p-1")
        mock_provider = Provider(id="p-1", key="dummy-key", name="dummy", base_url="http://dummy", api_key="sk-fake")

        with patch("app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.side_effect = RuntimeError("LLM failure")

            res = await compact_tiered_memory(
                session_id="s-fall",
                db=db,
                agent_model=mock_model,
                provider=mock_provider,
                hot_window=2,
                org_id="org-fall",
            )

            assert "Fallback msg 1" in res["warm"]
            assert "Fallback msg 3" in res["hot"]


@pytest.mark.asyncio
async def test_agent_loop_tiered_memory_runtime_integration(async_session_factory):
    from unittest.mock import patch

    from app.core.agent_loop import run_agent_loop
    from app.models.agent import Agent
    from app.models.memory import AgentMemory
    from app.models.session import Session
    from app.models.user import User

    async with async_session_factory() as db:
        u = User(id="u-int", email="int@example.com", display_name="Int User", is_active=True)
        prov = Provider(id="p-int", org_id="org-int", key="p-key", name="p-name", base_url="http://test", api_key="sk-fake")
        mdl = Model(id="m-int", org_id="org-int", provider_id="p-int", name="m-name", display_name="m-name")
        ag = Agent(
            id="agent-int",
            org_id="org-int",
            name="Tiered Memory Agent",
            model_id="m-int",
            created_by_user_id="u-int",
        )
        mem = AgentMemory(
            id="mem-int",
            org_id="org-int",
            agent_id="agent-int",
            memory_type="user",
            attribute="framework",
            value="FastAPI",
            importance=5,
        )
        sess = Session(
            id="s-runtime",
            org_id="org-int",
            agent_id="agent-int",
            created_by_user_id="u-int",
            title="Runtime Session",
        )
        db.add_all([u, prov, mdl, ag, mem, sess])

        # Create 22 messages to exceed compact_tiered_memory threshold (>20)
        for i in range(1, 23):
            db.add(
                Message(
                    org_id="org-int",
                    session_id="s-runtime",
                    role="user" if i % 2 != 0 else "assistant",
                    content=f"History turn {i}",
                    position=i,
                )
            )
        await db.commit()

    captured_prompt_messages = []

    async def mock_stream(messages, *args, **kwargs):
        captured_prompt_messages.extend(messages)
        yield {"type": "content", "text": "I recall tiered memory"}
        yield {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 10}, "estimated": False}

    async def mock_complete(*args, **kwargs):
        return ("Warm rolling transcript summary", 10, 0.001)

    async with async_session_factory() as db:
        res_agent = await db.get(Agent, "agent-int")
        with (
            patch("app.core.llm.LLMClient.stream", side_effect=mock_stream),
            patch("app.core.memory.tiers.LLMClient.complete", side_effect=mock_complete),
        ):
            res_loop = await run_agent_loop(
                agent=res_agent,
                message="Current turn prompt",
                db=db,
                session_id="s-runtime",
                user_id="u-int",
            )
            assert res_loop.content == "I recall tiered memory"

    # Verify that tiered combined memory was injected into system context
    sys_msgs = [m for m in captured_prompt_messages if m.get("role") == "system"]
    combined_sys_text = "\n".join(m.get("content", "") for m in sys_msgs)

    assert "[Cold Memory / User Profile]" in combined_sys_text
    assert "user.framework: FastAPI" in combined_sys_text
    assert "[Warm Memory / Session Summary]" in combined_sys_text
    assert "Warm rolling transcript summary" in combined_sys_text
    assert "[Hot Memory / Recent Turn]" in combined_sys_text


@pytest.mark.asyncio
async def test_compact_tiered_memory_resolves_org_and_user_from_session(async_session_factory):
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import select

    from app.models.memory import SessionMemory
    from app.models.organization import Organization
    from app.models.session import Session

    async with async_session_factory() as db:
        org = Organization(id="org-resolve", name="Resolve Org", slug="resolve-org")
        sess = Session(
            id="s-resolve",
            org_id="org-resolve",
            agent_id="ag-resolve",
            created_by_user_id="u-resolve",
            title="Resolv Session",
        )
        db.add_all([org, sess])

        for i in range(1, 5):
            db.add(
                Message(
                    org_id="org-resolve",
                    session_id="s-resolve",
                    role="user" if i % 2 != 0 else "assistant",
                    content=f"Resolv Message {i}",
                    position=i,
                )
            )
        await db.commit()

        mock_model = Model(id="m-1", name="dummy-model", provider_id="p-1")
        mock_provider = Provider(id="p-1", key="dummy-key", name="dummy", base_url="http://dummy", api_key="sk-fake")

        with patch("app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = ("Resolved warm summary", 10, 0.001)

            # Call WITHOUT org_id or created_by_user_id explicitly passed
            res = await compact_tiered_memory(
                session_id="s-resolve",
                db=db,
                agent_model=mock_model,
                provider=mock_provider,
                hot_window=2,
            )

            assert res["warm"] == "Resolved warm summary"

            smem_res = await db.execute(
                select(SessionMemory).where(
                    SessionMemory.session_id == "s-resolve",
                    SessionMemory.key == "warm_summary",
                )
            )
            smem = smem_res.scalar_one_or_none()
            assert smem is not None
            assert smem.org_id == "org-resolve"
            assert smem.created_by_user_id == "u-resolve"


@pytest.mark.asyncio
async def test_compact_tiered_memory_raises_without_org_id(async_session_factory):
    async with async_session_factory() as db:
        mock_model = Model(id="m-1", name="dummy-model", provider_id="p-1")
        mock_provider = Provider(id="p-1", key="dummy-key", name="dummy", base_url="http://dummy", api_key="sk-fake")

        with pytest.raises(ValueError, match="org_id is required"):
            await compact_tiered_memory(
                session_id="s-nonexistent",
                db=db,
                agent_model=mock_model,
                provider=mock_provider,
                hot_window=2,
            )
