"""Tests for the session event log append/load API."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import session_log as slog
from app.db.base import Base
from app.models.memory import SessionMemory  # noqa: F401  (ensures metadata complete)
from app.models.organization import Organization
from app.models.session import Session
from app.models.session_event import SessionEvent


@pytest.fixture
async def db_factory():
    # StaticPool: one shared in-memory SQLite connection, so MAX(seq) reads
    # and INSERTs always hit the same database (default pooling gives each
    # checkout its own empty :memory: database).
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


@pytest.fixture
async def seeded_session(db_factory):
    async with db_factory() as db:
        db.add(Organization(id="org-ev", name="Ev Org", slug="ev-org"))
        db.add(Session(id="s-ev", org_id="org-ev", agent_id="ag-ev", title="t"))
        await db.commit()
    return "org-ev", "s-ev"


@pytest.mark.asyncio
async def test_append_assigns_contiguous_seqs(db_factory, seeded_session):
    org_id, session_id = seeded_session
    async with db_factory() as db:
        s1 = await slog.append_event(
            db, session_id=session_id, org_id=org_id, type_=slog.USER_MESSAGE, data={"content": "a"}
        )
        s2 = await slog.append_event(
            db, session_id=session_id, org_id=org_id, type_=slog.ASSISTANT_MESSAGE, data={"content": "b"}
        )
        s3 = await slog.append_event(
            db, session_id=session_id, org_id=org_id, type_=slog.USER_MESSAGE, data={"content": "c"}
        )
        await db.commit()
        assert (s1, s2, s3) == (0, 1, 2)

        events = await slog.load_events(db, session_id)
        slog.assert_contiguous(events)
        assert [e.type for e in events] == [slog.USER_MESSAGE, slog.ASSISTANT_MESSAGE, slog.USER_MESSAGE]


@pytest.mark.asyncio
async def test_load_events_after_seq(db_factory, seeded_session):
    org_id, session_id = seeded_session
    async with db_factory() as db:
        for i in range(5):
            await slog.append_event(
                db, session_id=session_id, org_id=org_id, type_=slog.USER_MESSAGE, data={"content": str(i)}
            )
        await db.commit()
        events = await slog.load_events(db, session_id, after_seq=2)
        assert [e.seq for e in events] == [3, 4]


@pytest.mark.asyncio
async def test_unknown_type_rejected_at_append(db_factory, seeded_session):
    org_id, session_id = seeded_session
    async with db_factory() as db:
        with pytest.raises(slog.SessionEventError, match="unknown session event type"):
            await slog.append_event(db, session_id=session_id, org_id=org_id, type_="bogus/type", data={})


@pytest.mark.asyncio
async def test_lossless_json_validation_rejects_bad_payload(db_factory, seeded_session):
    org_id, session_id = seeded_session
    async with db_factory() as db:
        bad_payload = {"nested": {"value": {1, 2}}}  # a set is not JSON-round-trippable
        with pytest.raises(slog.SessionEventError, match="not losslessly serializable"):
            await slog.append_event(
                db, session_id=session_id, org_id=org_id, type_=slog.USER_MESSAGE, data=bad_payload
            )


@pytest.mark.asyncio
async def test_replace_surface_op_requires_source_seqs(db_factory, seeded_session):
    org_id, session_id = seeded_session
    async with db_factory() as db:
        with pytest.raises(slog.SessionEventError, match="source_seqs"):
            await slog.append_event(
                db,
                session_id=session_id,
                org_id=org_id,
                type_=slog.COMPACTION_SUMMARY,
                data={
                    "content": "x",
                    "surface_op": {"op": "replace", "start_seq": 0, "end_seq": 1},
                    # source_seqs missing
                },
            )
        seq = await slog.append_event(
            db,
            session_id=session_id,
            org_id=org_id,
            type_=slog.COMPACTION_SUMMARY,
            data={
                "content": "x",
                "surface_op": {"op": "replace", "start_seq": 0, "end_seq": 1},
                "source_seqs": [0, 1],
            },
        )
        await db.commit()
        assert seq == 0


@pytest.mark.asyncio
async def test_unique_constraint_blocks_concurrent_same_seq(db_factory, seeded_session):
    """Two overlapping writers must not fork the log - the unique index wins."""
    org_id, session_id = seeded_session
    async with db_factory() as db:
        await slog.append_event(
            db, session_id=session_id, org_id=org_id, type_=slog.USER_MESSAGE, data={"content": "first"}
        )
        # Simulate a second writer that computed the same next-seq before the
        # first committed: force a duplicate seq directly.
        db.add(SessionEvent(org_id=org_id, session_id=session_id, seq=0, type=slog.USER_MESSAGE, data={}))
        raised = False
        try:
            await db.commit()
        except Exception:  # noqa: BLE001 - IntegrityError family differs by driver
            raised = True
            await db.rollback()
        assert raised

        events = (await db.execute(select(SessionEvent).order_by(SessionEvent.seq))).scalars().all()
        # The whole transaction rolled back atomically - no partial fork.
        assert len(events) == 0
