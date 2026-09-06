"""Client Tool Bridge: the Redis-backed wait/post roundtrip and the ui_*
tool dispatch shape (emit -> wait -> structured result/timeout).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.core.tools import ui_bridge
from app.core.tools.registry import get_tool
from app.core.tools.types import ToolContext


class _FakeRedis:
    """Minimal in-memory stand-in for the two Redis ops the bridge uses."""

    def __init__(self):
        self._lists: dict[str, list[str]] = {}

    async def rpush(self, key: str, value: str) -> None:
        self._lists.setdefault(key, []).append(value)

    async def expire(self, key: str, ttl: int) -> None:
        pass

    async def blpop(self, keys: list[str], timeout: int):
        key = keys[0]
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self._lists.get(key):
                return key, self._lists[key].pop(0)
            await asyncio.sleep(0.01)
        return None


async def _resolved(value):
    return value


@pytest.fixture(autouse=True)
def _fake_bridge_client(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(ui_bridge, "_get_client", lambda: _resolved(fake))
    yield


async def test_wait_for_result_returns_posted_payload():
    call_id = "abc123"
    await ui_bridge.post_result(call_id, {"ok": True, "result": {"route": "/reports"}})
    result = await ui_bridge.wait_for_result(call_id, timeout_s=2)
    assert result == {"ok": True, "result": {"route": "/reports"}}


async def test_wait_for_result_times_out_with_structured_error():
    result = await ui_bridge.wait_for_result("never-posted", timeout_s=1)
    assert result == {"ok": False, "error": "ui_timeout"}


async def test_ui_navigate_dispatches_emit_then_waits_for_browser_result():
    spec = get_tool("ui_navigate")
    assert spec is not None
    assert spec.risk_tier.value == "safe"
    assert spec.requires_approval is False

    emitted: list[dict] = []

    async def _emit(ev):
        emitted.append(ev)
        # Simulate the browser answering the call it was just told about.
        await ui_bridge.post_result(ev["call_id"], {"ok": True, "result": {"route": ev["args"]["route"]}})

    ctx = ToolContext(db=None, emit=_emit)  # type: ignore[arg-type]
    result = await spec.run({"route": "/reports"}, ctx)

    assert len(emitted) == 1
    assert emitted[0]["type"] == "ui_action"
    assert emitted[0]["tool"] == "ui_navigate"
    assert json.loads(result) == {"route": "/reports"}


async def test_ui_navigate_missing_route_is_a_validation_error():
    spec = get_tool("ui_navigate")
    assert spec is not None
    ctx = ToolContext(db=None)  # type: ignore[arg-type]
    result = await spec.run({}, ctx)
    assert result.startswith("error:")


async def test_ui_submit_form_requires_approval():
    spec = get_tool("ui_submit_form")
    assert spec is not None
    assert spec.requires_approval is True
    assert spec.risk_tier.value == "write"
