"""Client Tool Bridge: lets a ``ui.*`` tool run *in the browser* instead of
on the server.

A ``ui.*`` tool's ``run()`` emits a ``ui_action`` progress event (delivered to
the browser over the existing chat SSE stream) carrying a ``call_id``, then
blocks on this module's ``wait_for_result`` until the browser reports back
via ``POST /api/chat/runs/{run_id}/ui-result``.

Redis (not an in-process ``asyncio.Event``) is required because the chat run
issuing the tool call may execute in the ``worker`` process while the
POST answering it lands in the ``api`` process.
"""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings

_KEY_PREFIX = "openagent:ui_result:"
# Safety net only: BLPOP already removes the key the instant a result is
# consumed. This bounds how long an unclaimed result (posted after the
# waiting tool already gave up on timeout) lingers in Redis.
_RESULT_TTL_SECONDS = 60

_client: Any = None


async def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    from redis.asyncio import from_url

    _client = from_url(get_settings().redis_url, decode_responses=True)
    return _client


def _key(call_id: str) -> str:
    return f"{_KEY_PREFIX}{call_id}"


async def wait_for_result(call_id: str, timeout_s: float) -> dict[str, Any]:
    """Block until the browser posts a result for ``call_id``, or time out.

    Returns the posted payload, or a structured ``{"ok": False, "error":
    "ui_timeout"}`` on timeout so the calling tool can hand the agent a clear
    error instead of the run hanging or raising.
    """
    client = await _get_client()
    try:
        item = await client.blpop([_key(call_id)], timeout=max(1, int(timeout_s)))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ui_bridge_unavailable: {exc}"}
    if item is None:
        return {"ok": False, "error": "ui_timeout"}
    _, raw = item
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {"ok": False, "error": "ui_result_malformed"}


async def post_result(call_id: str, payload: dict[str, Any]) -> None:
    """Deliver a browser-side result to whichever tool is waiting on it.

    Safe to call even if nothing is waiting (e.g. the tool already timed
    out) — the value sits under a short TTL and is simply never read.
    """
    client = await _get_client()
    key = _key(call_id)
    await client.rpush(key, json.dumps(payload, ensure_ascii=False))
    await client.expire(key, _RESULT_TTL_SECONDS)
