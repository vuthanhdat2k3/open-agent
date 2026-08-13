from __future__ import annotations

import os

os.environ["OPENAGENT_DB_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAGENT_REDIS_URL"] = "redis://127.0.0.1:6379/15"
os.environ["OPENAGENT_WORKFLOW_EXECUTION_MODE"] = "inline"
os.environ["OPENAGENT_OTEL_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""

from app.config import get_settings

get_settings.cache_clear()

import pytest


@pytest.fixture(autouse=True)
def _skip_lifespan_db_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop TestClient lifespan from migrating the real database.

    ``app.main.lifespan`` calls ``init_db()`` against the global engine, which
    in the local .env points at a remote Postgres. Every TestClient runs its
    own event loop; asyncpg connections pooled by the global engine are bound
    to whichever loop created them, so the next TestClient reuses a stale
    connection and crashes at startup with "Event loop is closed". Tests
    exercise DB logic through their own in-memory engines (get_db overrides),
    so the production migration is unnecessary and harmful here.
    """
    import app.main as main

    async def _noop_init_db() -> None:
        return None

    monkeypatch.setattr(main, "init_db", _noop_init_db)
    yield


@pytest.fixture(autouse=True)
def _no_ci_auto_research_enqueue(monkeypatch: pytest.MonkeyPatch):
    """Do not enqueue real Redis jobs from sync_connection during tests.

    Every test that exercises sync_connection/run_due_schedules otherwise
    enqueues a real ARQ job against the test Redis DB (index 15) that no
    worker ever consumes. Tests that specifically want to assert on
    enqueue behavior (tests/test_ci_auto_research.py) override this with
    their own monkeypatch, which takes precedence since it runs later.
    """

    async def _noop_enqueue(org_id: str, case_id: str) -> str:
        return ""

    monkeypatch.setattr(
        "app.customer_intelligence.ingest.enqueue_ci_research", _noop_enqueue
    )


@pytest.fixture(autouse=True)
def ci_mcp_stub(monkeypatch: pytest.MonkeyPatch):
    state = {"drafts": {}, "sent": {}, "next": 0}

    async def call(tool: str, args: dict):
        if tool == "email_history_checkpoint":
            return {"history_id": "checkpoint-1"}
        if tool == "email_list_new":
            state["next"] += 1
            return {
                "messages": [{
                    "provider": args["provider"],
                    "provider_message_id": f"mcp-message-{state['next']}",
                    "thread_id": None,
                    "sender_name": "Sales",
                    "sender_email": "sales@acme.example",
                    "sender_domain": "acme.example",
                    "recipients": ["user@example.com"],
                    "subject": "Customer request",
                    "body_text": "Please send a quote.",
                    "body_html": None,
                    "attachments": [],
                    "received_at": "2026-08-06T00:00:00+00:00",
                    "headers": {},
                }],
                "new_cursor": "1",
                "has_more": False,
            }
        if tool == "email_create_draft":
            draft_id = f"draft-{len(state['drafts']) + 1}"
            state["drafts"][draft_id] = args
            return {"draft_id": draft_id}
        if tool == "email_send":
            key = args["idempotency_key"]
            state["sent"].setdefault(key, f"send-{len(state['sent']) + 1}")
            return {"send_id": state["sent"][key]}
        if tool == "email_get":
            return (await call("email_list_new", args))["messages"][0]
        raise AssertionError(f"unexpected MCP tool: {tool}")

    monkeypatch.setattr("app.customer_intelligence.providers.email.call_customer_intelligence_mcp", call)
    monkeypatch.setattr("app.customer_intelligence.providers.research.call_customer_intelligence_mcp", call)
    return state
