from __future__ import annotations

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.customer_intelligence import CiNotification, InboundEmail


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


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


def _register(client: TestClient) -> tuple[str, str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": "inbox-test@example.com", "password": "Secret123!", "org_name": "InboxOrg"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["memberships"][0]["org_id"], me.json()["id"]


def _seed_notifications(async_session_factory, org_id: str, user_id: str) -> None:
    async def _seed() -> None:
        from datetime import datetime, timedelta

        async with async_session_factory() as session:
            for index in range(3):
                received_at = datetime(2026, 8, 13, 10, 0) + timedelta(minutes=index)
                email = InboundEmail(
                    org_id=org_id,
                    provider="gmail",
                    provider_message_id=f"message-{index}",
                    sender_email=f"sender-{index}@example.com",
                    sender_domain="example.com",
                    subject=f"Subject {index}",
                    body_text=f"Searchable body {index}",
                    received_at=received_at,
                )
                session.add(email)
                await session.flush()
                session.add(
                    CiNotification(
                        org_id=org_id,
                        user_id=user_id,
                        email_id=email.id,
                        notification_type="email_received",
                        title=f"New email from sender-{index}@example.com",
                        body=f"Subject {index}\nSearchable body {index}",
                        created_at=received_at,
                    )
                )
            await session.commit()

    anyio.run(_seed)


def test_notifications_are_newest_first_and_cursor_paginated(client, async_session_factory, ci_enabled):
    token, org_id, user_id = _register(client)
    _seed_notifications(async_session_factory, org_id, user_id)
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    first = client.get("/api/customer-intelligence/notifications?limit=2", headers=headers)
    assert first.status_code == 200, first.text
    payload = first.json()
    assert [item["subject"] for item in payload["items"]] == ["Subject 2", "Subject 1"]
    assert payload["total"] == 3
    assert payload["has_more"] is True

    second = client.get(
        f"/api/customer-intelligence/notifications?limit=2&cursor={payload['next_cursor']}",
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert [item["subject"] for item in second.json()["items"]] == ["Subject 0"]


def test_notifications_search_is_server_side_filtered(client, async_session_factory, ci_enabled):
    token, org_id, user_id = _register(client)
    _seed_notifications(async_session_factory, org_id, user_id)
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}

    response = client.get(
        "/api/customer-intelligence/notifications?q=sender-1", headers=headers
    )
    assert response.status_code == 200, response.text
    assert [item["subject"] for item in response.json()["items"]] == ["Subject 1"]
