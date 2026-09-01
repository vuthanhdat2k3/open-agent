from __future__ import annotations

import os

# The project ships a parent ``.env`` that activates the ZITADEL identity
# provider, which would 404 every legacy /api/auth/* endpoint used by the
# in-process test client. Pin the local provider for the whole test run so
# each test gets the expected legacy surface regardless of the developer's
# shell or parent .env.
os.environ.setdefault("OPENAGENT_AUTH_PROVIDER", "local")
os.environ["OPENAGENT_DB_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAGENT_REDIS_URL"] = "redis://:695ddab0ea43f1fc2fbf57d3ee559620709b4d7405557c92f759f5fa4c8fa5fd@127.0.0.1:6379/15"
os.environ["OPENAGENT_WORKFLOW_EXECUTION_MODE"] = "inline"
os.environ["OPENAGENT_OTEL_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""

from app.config import get_settings

get_settings.cache_clear()

import pytest


@pytest.fixture(autouse=True)
def _fake_agent_classifier_for_ingest_tests(monkeypatch: pytest.MonkeyPatch):
    """Use a deterministic agent result for sync tests; never call a real LLM."""
    from app.customer_intelligence.classifier import Classification

    async def _classify(_db, _org_id, email):
        if email.injection_flags:
            return Classification("security_risk", 1.0, "guard flagged untrusted instruction content")
        return Classification(
            "customer", 0.96, "fixture: customer request", company_name="Acme", company_domain="acme.example",
            company_confidence=0.92,
        )

    monkeypatch.setattr(
        "app.customer_intelligence.classification_service.classify_with_agent", _classify
    )


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

    async def _noop_sync_system_agents(_db):
        return []

    async def _noop_sync_system_workflows(_db):
        return []

    monkeypatch.setattr(main, "init_db", _noop_init_db)
    monkeypatch.setattr(main, "sync_system_agents_all_orgs", _noop_sync_system_agents)
    monkeypatch.setattr(main, "sync_system_workflow_templates", _noop_sync_system_workflows)
    yield


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
