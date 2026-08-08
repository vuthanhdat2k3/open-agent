"""Fail-open contract for the chat event bus.

Live streaming fans out over Redis pub/sub, but a Redis outage must never break
a chat run: publishing has to degrade silently to the durable log (which the
follower then polls). These tests lock that contract, plus the circuit breaker
that keeps a dead Redis from costing a connect timeout on every single event --
without it the "fallback" would be slower than having no bus at all.
"""

from __future__ import annotations

import pytest

from app.core import chat_events as bus
from app.core.observability.metrics import chat_event_bus_failures_total


def _failure_count() -> float:
    return chat_event_bus_failures_total.labels("publish")._value.get()


@pytest.fixture(autouse=True)
def _reset_bus_state():
    """Module globals are process-wide; isolate each test from the others."""
    bus._bus_client = None
    bus._bus_breaker_until = 0.0
    bus._record_times.clear()
    yield
    bus._bus_client = None
    bus._bus_breaker_until = 0.0
    bus._record_times.clear()


@pytest.mark.asyncio
async def test_publish_failure_does_not_raise_and_is_counted(monkeypatch):
    async def boom():
        raise ConnectionError("redis is down")

    monkeypatch.setattr(bus, "_get_bus_client", boom)
    before = _failure_count()

    # Must not raise: the agent loop calls this inline while streaming.
    await bus.publish_run_event("org-1", "run-1", {"seq": 1, "event": "token", "data": {}})

    assert _failure_count() == before + 1
    assert not bus._bus_available(), "a failure must trip the breaker"


@pytest.mark.asyncio
async def test_breaker_skips_further_publishes_instead_of_retrying(monkeypatch):
    calls = 0

    async def boom():
        nonlocal calls
        calls += 1
        raise ConnectionError("redis is down")

    monkeypatch.setattr(bus, "_get_bus_client", boom)

    await bus.publish_run_event("org-1", "run-1", {"seq": 1, "event": "token", "data": {}})
    assert calls == 1

    # While the breaker is open every publish returns immediately. If this
    # regressed, a dead Redis would add its connect timeout to every token.
    for seq in range(2, 6):
        await bus.publish_run_event("org-1", "run-1", {"seq": seq, "event": "token", "data": {}})
    assert calls == 1, "breaker should short-circuit without touching the client"


@pytest.mark.asyncio
async def test_breaker_recovers_once_the_cooldown_expires(monkeypatch):
    async def boom():
        raise ConnectionError("redis is down")

    monkeypatch.setattr(bus, "_get_bus_client", boom)
    await bus.publish_run_event("org-1", "run-1", {"seq": 1, "event": "token", "data": {}})
    assert not bus._bus_available()

    # Simulate the cooldown elapsing rather than sleeping through it.
    bus._bus_breaker_until = 0.0
    assert bus._bus_available(), "the bus must be retried after the cooldown"


@pytest.mark.asyncio
async def test_recorder_still_queues_the_durable_row_when_the_bus_is_down(monkeypatch):
    async def boom():
        raise ConnectionError("redis is down")

    monkeypatch.setattr(bus, "_get_bus_client", boom)

    recorder = bus.ChatEventRecorder("org-1", "run-1", session_id="sess-1")

    async def _no_flush() -> None:
        """The durable write is covered by the e2e tests; keep this unit test
        off the database while still letting the batch timer await it."""

    monkeypatch.setattr(recorder, "_flush", _no_flush)

    event = {"event": "token", "data": {"delta": "hi"}}
    returned = await recorder.record(event)

    assert returned is event, "record() must pass the event through untouched"
    assert recorder.seq == 1
    assert len(recorder._pending) == 1
    assert recorder._pending[0].event == "token"

    # record() schedules the batch timer as a background task. Leaving it
    # pending when this test's event loop closes leaks into whichever test runs
    # next, so shut it down explicitly.
    await recorder.close()
