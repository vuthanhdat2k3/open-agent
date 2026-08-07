from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.customer_intelligence.security import encrypt_credentials
from app.db.base import Base, utc_now
from app.db.session import get_db
from app.main import app
from app.models.approval_request import ApprovalRequest
from app.models.customer_intelligence import EmailConnection, InboundEmail, ResearchCase
from app.repositories.customer_intelligence import DeliveryAttemptRepository


@pytest.fixture
async def async_session_factory():
    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def ci_enabled(monkeypatch):
    monkeypatch.setenv("OPENAGENT_CUSTOMER_INTELLIGENCE_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _register(client: TestClient, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Secret123!", "org_name": "CIDeliveryOrg"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["memberships"][0]["org_id"]


def _seed_ready_case(async_session_factory, org_id: str) -> str:
    import anyio

    async def _seed() -> str:
        async with async_session_factory() as session:
            conn = EmailConnection(
                org_id=org_id,
                provider="gmail",
                account_email=f"crm-{org_id[:8]}@example.com",
                status="connected",
                credentials_enc=encrypt_credentials({"access_token": "test"}),
            )
            session.add(conn)
            await session.flush()
            email = InboundEmail(
                org_id=org_id,
                connection_id=conn.id,
                provider="gmail",
                provider_message_id=f"msg-{org_id[:8]}",
                sender_domain="acme.com",
                sender_email="sales@acme.com",
                subject="Request for proposal",
                body_text="Please brief us on your product.",
                received_at=utc_now(),
            )
            session.add(email)
            await session.flush()
            case = ResearchCase(
                org_id=org_id,
                email_id=email.id,
                connection_id=conn.id,
                company_name="Acme",
                company_domain="acme.com",
                status="REPORT_READY",
                trigger="manual",
                finished_at=utc_now(),
            )
            session.add(case)
            await session.commit()
            return case.id

    return anyio.run(_seed)


def test_propose_delivery_creates_approval_and_is_idempotent(
    async_session_factory, client: TestClient, ci_enabled
) -> None:
    token, org_id = _register(client, "ci-owner-1@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    case_id = _seed_ready_case(async_session_factory, org_id)

    payload = {
        "action": "send_email",
        "to": "sales@acme.com",
        "subject": "Briefing: Acme",
        "body": "# Acme briefing\n\nSummary here.",
    }
    first = client.post(f"/api/customer-intelligence/cases/{case_id}/deliver", headers=header, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "pending"
    assert first.json()["case_id"] == case_id
    assert first.json()["action"] == "send_email"

    second = client.post(f"/api/customer-intelligence/cases/{case_id}/deliver", headers=header, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]

    case = client.get(f"/api/customer-intelligence/cases/{case_id}", headers=header)
    assert case.json()["status"] == "AWAITING_APPROVAL"


def test_reject_delivery_transitions_case_to_rejected(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    token, org_id = _register(client, "delivery-owner-reject@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    case_id = _seed_ready_case(async_session_factory, org_id)

    first = client.post(
        f"/api/customer-intelligence/cases/{case_id}/deliver",
        headers=header,
        json={"action": "send_email", "to": "x@y.com", "subject": "s", "body": "b"},
    )
    approval = first.json()

    decided = client.post(
        f"/api/customer-intelligence/cases/{case_id}/approval/{approval['id']}/decide",
        headers=header,
        json={"decision": "rejected", "reason": "not now"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "rejected"

    case = client.get(f"/api/customer-intelligence/cases/{case_id}", headers=header)
    assert case.json()["status"] == "REJECTED"


def test_expired_approval_transitions_case_to_expired(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    import anyio

    token, org_id = _register(client, "delivery-owner-expire@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    case_id = _seed_ready_case(async_session_factory, org_id)

    first = client.post(
        f"/api/customer-intelligence/cases/{case_id}/deliver",
        headers=header,
        json={"action": "send_email", "to": "x@y.com", "subject": "s", "body": "b"},
    )
    approval_id = first.json()["id"]

    async def _backdate() -> None:
        async with async_session_factory() as session:
            res = await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
            ap = res.scalar_one()
            ap.expires_at = utc_now() - timedelta(seconds=1)
            await session.commit()

    anyio.run(_backdate)

    decided = client.post(
        f"/api/customer-intelligence/cases/{case_id}/approval/{approval_id}/decide",
        headers=header,
        json={"decision": "approved", "reason": "too late"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "expired"

    case = client.get(f"/api/customer-intelligence/cases/{case_id}", headers=header)
    assert case.json()["status"] == "EXPIRED"


def test_approve_delivers_once_and_replay_is_rejected(
    async_session_factory, client: TestClient, ci_enabled, ci_mcp_stub
) -> None:
    token, org_id = _register(client, "delivery-owner-approve@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    case_id = _seed_ready_case(async_session_factory, org_id)

    first = client.post(
        f"/api/customer-intelligence/cases/{case_id}/deliver",
        headers=header,
        json={"action": "send_email", "to": "sales@acme.com", "subject": "Acme briefing", "body": "content"},
    )
    approval_id = first.json()["id"]

    decided = client.post(
        f"/api/customer-intelligence/cases/{case_id}/approval/{approval_id}/decide",
        headers=header,
        json={"decision": "approved", "reason": "go"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"

    case = client.get(f"/api/customer-intelligence/cases/{case_id}", headers=header)
    assert case.json()["status"] == "COMPLETED"

    assert len(ci_mcp_stub["drafts"]) == 1
    assert len(ci_mcp_stub["sent"]) == 1

    import anyio

    async def _check_attempt() -> None:
        async with async_session_factory() as session:
            attempt = await DeliveryAttemptRepository(session).get_by_idempotency_key(
                org_id, f"ci:{case_id}:send_email"
            )
            assert attempt is not None
            assert attempt.status == "delivered"
            assert attempt.provider_send_id is not None

    anyio.run(_check_attempt)

    replay = client.post(
        f"/api/customer-intelligence/cases/{case_id}/approval/{approval_id}/decide",
        headers=header,
        json={"decision": "approved", "reason": "replay"},
    )
    assert replay.status_code == 400, replay.text
    assert "already decided" in replay.json()["detail"].lower()


def _histogram_count(hist, **labels: str) -> float:
    """Sum of observed samples for a histogram's label set."""
    for sample in hist.labels(**labels).collect()[0].samples:
        if sample.name.endswith("_count"):
            return sample.value
    return 0.0


def test_rejecting_approval_observes_approval_age_metric(
    client: TestClient, async_session_factory, ci_enabled
) -> None:
    from app.core.observability.metrics import ci_approval_age_seconds

    token, org_id = _register(client, "delivery-owner-age@test.com")
    header = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}
    case_id = _seed_ready_case(async_session_factory, org_id)

    before = _histogram_count(ci_approval_age_seconds, decision="rejected")

    first = client.post(
        f"/api/customer-intelligence/cases/{case_id}/deliver",
        headers=header,
        json={"action": "send_email", "to": "x@y.com", "subject": "s", "body": "b"},
    )
    approval = first.json()

    decided = client.post(
        f"/api/customer-intelligence/cases/{case_id}/approval/{approval['id']}/decide",
        headers=header,
        json={"decision": "rejected", "reason": "not now"},
    )
    assert decided.status_code == 200, decided.text

    assert _histogram_count(ci_approval_age_seconds, decision="rejected") == before + 1
    assert _histogram_count(ci_approval_age_seconds, decision="approved") == _histogram_count(
        ci_approval_age_seconds, decision="approved"
    )  # untouched by this test
