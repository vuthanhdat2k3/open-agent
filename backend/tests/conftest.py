from __future__ import annotations

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
def ci_mcp_stub(monkeypatch: pytest.MonkeyPatch):
    state = {"drafts": {}, "sent": {}, "next": 0}

    async def call(tool: str, args: dict):
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
