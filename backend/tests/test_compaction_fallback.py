"""Tests for safe compaction fallback and incremental warm summary."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import patch

from app.core.memory.tiers import (
    WARM_SUMMARY_KEY,
    WARM_SUMMARY_UPTO_KEY,
    compact_tiered_memory,
)
from app.db.base import Base
from app.models.memory import SessionMemory
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


def _mock_provider_model():
    return (
        Model(id="m-1", name="dummy-model", provider_id="p-1"),
        Provider(id="p-1", key="dummy-key", name="dummy", base_url="http://dummy", api_key="sk-fake"),
    )


async def _seed_messages(db: AsyncSession, org_id: str, session_id: str, n: int) -> None:
    for i in range(1, n + 1):
        db.add(
            Message(
                org_id=org_id,
                session_id=session_id,
                role="user" if i % 2 != 0 else "assistant",
                content=f"Fallback msg {i}",
                position=i,
            )
        )
    await db.commit()


async def _get_memory(db: AsyncSession, session_id: str, key: str) -> SessionMemory | None:
    res = await db.execute(
        select(SessionMemory).where(
            SessionMemory.session_id == session_id,
            SessionMemory.key == key,
        )
    )
    return res.scalar_one_or_none()


@pytest.mark.asyncio
async def test_summarizer_failure_returns_bounded_truncated_fallback(async_session_factory):
    from unittest.mock import AsyncMock

    async with async_session_factory() as db:
        await _seed_messages(db, "org-fb", "s-fb", 6)

        model, provider = _mock_provider_model()
        with patch(
            "app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.side_effect = RuntimeError("provider down")

            res = await compact_tiered_memory(
                session_id="s-fb",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-fb",
            )

            assert "[Unsummarized earlier conversation — truncated]" in res["warm"]
            # Bounded: never re-injects the full raw transcript beyond the cap.
            assert len(res["warm"]) < len("[Unsummarized earlier conversation — truncated]") + 6000 + 100
            # Hot tier untouched.
            assert "Fallback msg 5" in res["hot"] or "Fallback msg 6" in res["hot"]
            # Summarizer retried up to the attempt cap before falling back.
            assert mock_complete.await_count == 3


@pytest.mark.asyncio
async def test_context_overflow_error_is_not_retried(async_session_factory):
    from unittest.mock import AsyncMock

    async with async_session_factory() as db:
        await _seed_messages(db, "org-of", "s-of", 6)

        model, provider = _mock_provider_model()
        with patch(
            "app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.side_effect = RuntimeError("exceeds context length window")

            await compact_tiered_memory(
                session_id="s-of",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-of",
            )

            assert mock_complete.await_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure(async_session_factory):
    from unittest.mock import AsyncMock

    async with async_session_factory() as db:
        await _seed_messages(db, "org-retry", "s-retry", 6)

        model, provider = _mock_provider_model()
        responses = [RuntimeError("transient"), ("Recovered summary", 10, 0.001)]
        with patch(
            "app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.side_effect = responses

            res = await compact_tiered_memory(
                session_id="s-retry",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-retry",
            )

            assert res["warm"] == "Recovered summary"
            assert mock_complete.await_count == 2


@pytest.mark.asyncio
async def test_incremental_summary_only_sends_new_messages(async_session_factory):
    from unittest.mock import AsyncMock

    prompts: list[str] = []

    async def fake_complete(messages, *args, **kwargs):
        prompts.append(messages[-1]["content"])
        return (f"Summary #{len(prompts)}", 10, 0.001)

    async with async_session_factory() as db:
        await _seed_messages(db, "org-inc", "s-inc", 8)

        model, provider = _mock_provider_model()
        with patch("app.core.memory.tiers.LLMClient.complete", side_effect=fake_complete):
            # First compaction: messages 1..6 are older than the hot window of 2.
            await compact_tiered_memory(
                session_id="s-inc",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-inc",
            )

            smem = await _get_memory(db, "s-inc", WARM_SUMMARY_KEY)
            upto = await _get_memory(db, "s-inc", WARM_SUMMARY_UPTO_KEY)
            assert smem is not None and smem.value == "Summary #1"
            assert upto is not None
            first_upto = int(upto.value)
            assert first_upto == 6

            # New turns arrive.
            db.add_all(
                [
                    Message(org_id="org-inc", session_id="s-inc", role="user", content="Fresh A", position=9),
                    Message(org_id="org-inc", session_id="s-inc", role="assistant", content="Fresh B", position=10),
                ]
            )
            await db.commit()

            # Second compaction: hot window slides to 9/10, older now spans 1..8.
            res2 = await compact_tiered_memory(
                session_id="s-inc",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-inc",
            )

            assert res2["warm"] == "Summary #2"
            # The incremental prompt must contain the previous summary and ONLY
            # messages newer than the stored cursor - not the full transcript.
            second_prompt = prompts[1]
            assert f"Summary #{1}" in second_prompt or "Summary #1" in second_prompt
            assert "Fallback msg 7" in second_prompt
            assert "Fallback msg 8" in second_prompt
            assert "Fallback msg 1" not in second_prompt
            assert "Fresh A" not in second_prompt  # still inside the hot window

            upto2 = await _get_memory(db, "s-inc", WARM_SUMMARY_UPTO_KEY)
            assert upto2 is not None and upto2.value == "8"


@pytest.mark.asyncio
async def test_incremental_merge_failure_keeps_previous_summary_bounded(async_session_factory):
    from unittest.mock import AsyncMock

    async with async_session_factory() as db:
        await _seed_messages(db, "org-mrg", "s-mrg", 8)
        db.add(SessionMemory(org_id="org-mrg", session_id="s-mrg", key=WARM_SUMMARY_KEY, value="Durable prior summary"))
        db.add(SessionMemory(org_id="org-mrg", session_id="s-mrg", key=WARM_SUMMARY_UPTO_KEY, value="4"))
        await db.commit()

        model, provider = _mock_provider_model()
        with patch(
            "app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.side_effect = RuntimeError("merge failed")

            res = await compact_tiered_memory(
                session_id="s-mrg",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-mrg",
            )

            # Prior summary survives, plus a bounded truncated tail of the
            # newer unsummarized messages - not the full transcript.
            assert "Durable prior summary" in res["warm"]
            assert "[Unsummarized recent messages — truncated]" in res["warm"]
            assert len(res["warm"]) < 7000

            # Cursor stays at the last durably-summarized position.
            upto = await _get_memory(db, "s-mrg", WARM_SUMMARY_UPTO_KEY)
            assert upto is not None and upto.value == "4"


@pytest.mark.asyncio
async def test_legacy_warm_summary_without_cursor_uses_full_path(async_session_factory):
    from unittest.mock import AsyncMock

    async with async_session_factory() as db:
        await _seed_messages(db, "org-legacy", "s-legacy", 6)
        db.add(
            SessionMemory(
                org_id="org-legacy",
                session_id="s-legacy",
                key=WARM_SUMMARY_KEY,
                value="Legacy summary",
            )
        )
        await db.commit()

        model, provider = _mock_provider_model()
        with patch(
            "app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.return_value = ("Full-path summary", 10, 0.001)

            res = await compact_tiered_memory(
                session_id="s-legacy",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-legacy",
            )

            # No valid cursor -> full re-summarize of everything older than hot.
            assert res["warm"] == "Full-path summary"
            prompt = mock_complete.await_args.args[0][-1]["content"]
            assert "Legacy summary" not in prompt
            assert "Fallback msg 1" in prompt

            upto = await _get_memory(db, "s-legacy", WARM_SUMMARY_UPTO_KEY)
            assert upto is not None and upto.value == "4"


@pytest.mark.asyncio
async def test_invalid_cursor_value_falls_back_to_full_path(async_session_factory):
    from unittest.mock import AsyncMock

    async with async_session_factory() as db:
        await _seed_messages(db, "org-bad", "s-bad", 6)
        db.add(SessionMemory(org_id="org-bad", session_id="s-bad", key=WARM_SUMMARY_KEY, value="Prior summary"))
        db.add(SessionMemory(org_id="org-bad", session_id="s-bad", key=WARM_SUMMARY_UPTO_KEY, value="not-a-number"))
        await db.commit()

        model, provider = _mock_provider_model()
        with patch(
            "app.core.memory.tiers.LLMClient.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.return_value = ("Rebuilt summary", 10, 0.001)

            res = await compact_tiered_memory(
                session_id="s-bad",
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=2,
                org_id="org-bad",
            )

            assert res["warm"] == "Rebuilt summary"
            prompt = mock_complete.await_args.args[0][-1]["content"]
            assert "Prior summary" not in prompt
