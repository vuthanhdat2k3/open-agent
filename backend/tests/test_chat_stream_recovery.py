"""Chat stream recovery: the event recorder writes (not crashes) when the
global engine points elsewhere, the follow endpoint drains + closes on
terminal runs, and the orphan sweep fails silent chat tasks."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.chat_events as chat_events
from app.db.base import Base
from app.models.chat_run_event import ChatRunEvent
from app.models.organization import Organization
from app.models.task import Task


async def _init_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _mk_org_and_task(factory) -> tuple[str, str]:
    async with factory() as s:
        org = Organization(name="Acme", slug=f"acme-{id(s)}")
        s.add(org)
        await s.flush()
        task = Task(
            org_id=org.id,
            root_run_id="run-1",
            agent_id="a-1",
            goal="hello",
            status="running",
            progress={},
        )
        s.add(task)
        await s.commit()
        return org.id, task.id


@pytest.mark.asyncio
async def test_recorder_appends_events_with_monotonic_seq(session_factory, monkeypatch):
    monkeypatch.setattr(chat_events, "SessionLocal", session_factory)
    org_id, _ = await _mk_org_and_task(session_factory)

    rec = chat_events.ChatEventRecorder(org_id, "run-1")
    for i, name in enumerate(["message_start", "reasoning", "token", "message_done"]):
        ev = await rec.record({"event": name, "data": {"n": i}})
        assert ev["event"] == name  # pass-through
    await rec.close()

    async with session_factory() as s:
        rows = list(
            (await s.execute(select(ChatRunEvent).order_by(ChatRunEvent.seq))).scalars().all()
        )
    assert [r.seq for r in rows] == [1, 2, 3, 4]
    assert [r.event for r in rows] == ["message_start", "reasoning", "token", "message_done"]
    assert rows[2].data == {"n": 2}


@pytest.mark.asyncio
async def test_recorder_never_raises_without_a_database(monkeypatch):
    # Global SessionLocal points at the (unreachable) real DB here: recording
    # must degrade silently, never fail the user's run.
    rec = chat_events.ChatEventRecorder("org-x", "run-x")
    await rec.record({"event": "token", "data": {"content": "hi"}})
    await rec.flush_progress(phase="answering")
    await rec.close()


@pytest.mark.asyncio
async def test_flush_progress_stamps_task_checkpoint(session_factory, monkeypatch):
    monkeypatch.setattr(chat_events, "SessionLocal", session_factory)
    org_id, task_id = await _mk_org_and_task(session_factory)

    rec = chat_events.ChatEventRecorder(org_id, "run-1")
    await rec.record({"event": "token", "data": {}})
    await rec.flush_progress(phase="answering", content_chars=42)
    await rec.close()

    async with session_factory() as s:
        task = await s.get(Task, task_id)
    assert task.progress["phase"] == "answering"
    assert task.progress["content_chars"] == 42
    assert task.progress["last_seq"] == 1
    assert "updated_at" in task.progress


@pytest.mark.asyncio
async def test_list_events_filters_after_seq_and_scopes_org(session_factory):
    org_id, _ = await _mk_org_and_task(session_factory)
    async with session_factory() as s:
        for i in range(1, 5):
            s.add(
                ChatRunEvent(
                    org_id=org_id, run_id="run-1", seq=i, event="token", data={"n": i}
                )
            )
        # Same run id from another org must be invisible.
        s.add(
            ChatRunEvent(
                org_id="other-org", run_id="run-1", seq=99, event="token", data={"n": 99}
            )
        )
        await s.commit()

    async with session_factory() as s:
        rows = await chat_events.list_events(s, "run-1", org_id, after_seq=2)
    assert [r.seq for r in rows] == [3, 4]


@pytest.mark.asyncio
async def test_orphan_sweep_fails_only_stale_running_chat_tasks(session_factory):
    org_id, _ = await _mk_org_and_task(session_factory)
    async with session_factory() as s:
        res = await s.execute(select(Task).where(Task.org_id == org_id))
        stale = res.scalars().first()
        stale.progress = {"phase": "thinking", "updated_at": "2020-01-01T00:00:00"}
        # Freshtask: still running but heartbeat is recent -> must be left alone.
        fresh = Task(
            org_id=org_id,
            root_run_id="run-2",
            agent_id="a-1",
            goal="still alive",
            status="running",
            progress={
                "phase": "answering",
                "updated_at": "2999-01-01T00:00:00",
            },
        )
        s.add(fresh)
        await s.commit()

    async with session_factory() as s:
        failed = await chat_events.fail_orphaned_chat_runs(s)

    assert failed and len(failed) == 1
    async with session_factory() as s:
        orphaned = await s.get(Task, failed[0])
        assert orphaned.status == "failed"
        assert "worker lost" in (orphaned.result or "")
        fresh = (
            await s.execute(select(Task).where(Task.root_run_id == "run-2"))
        ).scalar_one()
        assert fresh.status == "running"
