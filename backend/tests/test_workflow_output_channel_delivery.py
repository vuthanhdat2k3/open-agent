"""The `output` node's `channel_connection_id`/`channel_recipient` config
must actually deliver to the connected Telegram/Discord channel.

New feature (not a bug-fix regression): lets a scheduled workflow report
straight into a chat via the same real `ChannelDriver.send_message` already
used by the `send_channel_message` chat tool.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.workflow.engine import _deliver_output_to_channel
from app.db.base import Base
from app.models.channel import ChannelConnection


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


class _FakeDriver:
    def __init__(self):
        self.sent = None

    async def send_message(self, recipient, content, **opts):
        self.sent = (recipient, content)
        return "external-id-1"


async def test_delivers_to_connected_channel_when_configured(monkeypatch, session_factory):
    fake_driver = _FakeDriver()
    monkeypatch.setattr(
        "app.channels.factory.build_channel_driver", lambda connection: fake_driver
    )

    async with session_factory() as db:
        connection = ChannelConnection(
            org_id="org-1", provider="telegram", bot_token_enc="enc", status="active"
        )
        db.add(connection)
        await db.commit()

        workflow = SimpleNamespace(id="wf-1", org_id="org-1")
        cfg = {"channel_connection_id": connection.id, "channel_recipient": "-100123"}
        await _deliver_output_to_channel(workflow, cfg, "the report text", db)

    assert fake_driver.sent == ("-100123", "the report text")


async def test_noop_when_not_configured(session_factory):
    async with session_factory() as db:
        workflow = SimpleNamespace(id="wf-1", org_id="org-1")
        # Should return cleanly with no channel_connection_id/recipient set —
        # no DB query, no driver built, no exception.
        await _deliver_output_to_channel(workflow, {}, "text", db)


async def test_never_raises_when_connection_missing(session_factory):
    async with session_factory() as db:
        workflow = SimpleNamespace(id="wf-1", org_id="org-1")
        cfg = {"channel_connection_id": "does-not-exist", "channel_recipient": "-100123"}
        # Must not raise — a broken channel config shouldn't fail the run.
        await _deliver_output_to_channel(workflow, cfg, "text", db)


async def test_never_raises_when_driver_send_fails(monkeypatch, session_factory):
    class _FailingDriver:
        async def send_message(self, recipient, content, **opts):
            raise RuntimeError("network error")

    monkeypatch.setattr(
        "app.channels.factory.build_channel_driver", lambda connection: _FailingDriver()
    )

    async with session_factory() as db:
        connection = ChannelConnection(
            org_id="org-1", provider="discord", bot_token_enc="enc", status="active"
        )
        db.add(connection)
        await db.commit()

        workflow = SimpleNamespace(id="wf-1", org_id="org-1")
        cfg = {"channel_connection_id": connection.id, "channel_recipient": "999"}
        await _deliver_output_to_channel(workflow, cfg, "text", db)
