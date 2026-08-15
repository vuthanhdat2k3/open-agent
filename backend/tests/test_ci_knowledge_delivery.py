from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.customer_intelligence.delivery import run_delivery
from app.customer_intelligence.security import encrypt_credentials
from app.db.base import Base, utc_now
from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import (
    BriefingReport,
    EmailConnection,
    InboundEmail,
    ResearchCase,
    ResearchSource,
)
from app.models.mcp import McpServer
from app.models.organization import Organization


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_knowledge_uses_org_collection_metadata_and_replays(
    async_session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeManager:
        async def call_tool(self, server, name: str, args: dict):
            calls.append((name, args))
            return "Ingested: briefing\n  Document ID: rag-document-1\n  Status: success"

    async def no_audit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.customer_intelligence.delivery.get_mcp_manager", lambda: FakeManager())
    monkeypatch.setattr("app.customer_intelligence.delivery.log_action", no_audit)

    async with async_session_factory() as session:
        org = Organization(id="org-knowledge", name="Knowledge Org", slug="knowledge-org")
        connection = EmailConnection(
            id="conn-knowledge",
            org_id=org.id,
            provider="gmail",
            account_email="owner@example.com",
            status="connected",
            credentials_enc=encrypt_credentials({"access_token": "test"}),
        )
        email = InboundEmail(
            id="email-knowledge",
            org_id=org.id,
            connection_id=connection.id,
            provider="gmail",
            provider_message_id="message-knowledge",
            sender_email="contact@acme.example",
            sender_domain="acme.example",
            subject="Briefing",
            body_text="Prepare a briefing.",
            received_at=utc_now(),
        )
        case = ResearchCase(
            id="case-knowledge",
            org_id=org.id,
            email_id=email.id,
            connection_id=connection.id,
            company_name="Acme",
            status="REPORT_READY",
        )
        report = BriefingReport(
            id="report-knowledge",
            org_id=org.id,
            case_id=case.id,
            version=2,
            canonical_markdown="# Acme briefing\n\nSummary.",
            rendering={"sections": "kept separate"},
        )
        source = ResearchSource(
            id="source-knowledge",
            org_id=org.id,
            case_id=case.id,
            url="https://acme.example/about",
            source_type="website",
            title="Acme About",
            excerpt="About Acme",
        )
        server = McpServer(id="rag-server-knowledge", org_id=org.id, name="rag", transport="sse", connection_status="connected")
        approval = ApprovalRequest(
            id="approval-knowledge",
            org_id=org.id,
            case_id=case.id,
            run_type="ci.delivery",
            tool_name="save_knowledge",
            status="approved",
            args_snapshot={},
            payload_hash="payload-hash",
            idempotency_key="ci:case-knowledge:save_knowledge",
        )
        session.add_all([org, connection, email, case, report, source, server, approval])
        await session.commit()

        first = await run_delivery(session, org_id=org.id, case=case, approval=approval)
        second = await run_delivery(session, org_id=org.id, case=case, approval=approval)

    assert first.id == second.id
    assert first.status == "delivered"
    assert first.provider_send_id == "rag-document-1"
    assert len(calls) == 1
    name, args = calls[0]
    assert name == "rag_ingest_text"
    assert args["collection"] == "ci-knowledge-org-knowledge"
    assert args["text"] == "# Acme briefing\n\nSummary."
    assert args["metadata"] == {
        "org_id": "org-knowledge",
        "case_id": "case-knowledge",
        "company_name": "Acme",
        "report_version": 2,
        "source_urls": ["https://acme.example/about"],
    }
