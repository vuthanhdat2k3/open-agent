"""Tier 2 tests for the workflow webhook endpoint (Phase 6)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.routes.workflow_webhooks import workflow_webhook
from app.config import get_settings
from app.db.base import Base
from app.models.organization import Organization
from app.models.outbox import OutboxEvent
from app.models.workflow_run import WorkflowRun
from app.services.workflow_service import WorkflowService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


class _FakeRequest:
    def __init__(self, body: bytes, token: str, content_length: int | None = None):
        self._body = body
        self.headers = {"x-webhook-token": token}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)

    async def body(self) -> bytes:
        return self._body


@pytest.mark.asyncio
async def test_webhook_fires_workflow(async_session_factory, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "workflow_webhook_shared_token", "test-token")

    async with async_session_factory() as session:
        org = Organization(name="Webhook Corp", slug="webhook-corp")
        session.add(org)
        await session.flush()
        wf = await WorkflowService(session).create(
            org.id,
            {
                "name": "Hook",
                "description": "",
                "graph": {
                    "nodes": [
                        {
                            "id": "in",
                            "kind": "integration",
                            "parameters": {"source": "webhook", "webhook_path": "deploy"},
                        },
                        {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
                    ],
                    "edges": [{"from_": "in", "to": "out"}],
                },
            },
            user_id="user-1",
        )
        req = _FakeRequest(b'{"event": "deploy", "repo": "app"}', "test-token")
        result = await workflow_webhook(wf.id, "deploy", req, session)
        assert result["accepted"] is True
        assert result["status"] == "queued"

        run = await session.scalar(
            select(WorkflowRun).where(WorkflowRun.id == result["workflow_run_id"])
        )
        assert run is not None
        assert run.status == "queued"
        assert run.input["webhook_payload"] == {"event": "deploy", "repo": "app"}
        assert run.input["path"] == "deploy"

        outbox = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "workflow.run.requested")
        )
        assert outbox is not None
        assert outbox.payload["run_id"] == result["workflow_run_id"]


@pytest.mark.asyncio
async def test_webhook_rejects_bad_token(async_session_factory, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "workflow_webhook_shared_token", "test-token")

    from fastapi import HTTPException

    async with async_session_factory() as session:
        org = Organization(name="Webhook Corp2", slug="webhook-corp2")
        session.add(org)
        await session.flush()
        wf = await WorkflowService(session).create(
            org.id,
            {
                "name": "Hook2",
                "description": "",
                "graph": {
                    "nodes": [
                        {
                            "id": "in",
                            "kind": "integration",
                            "parameters": {"source": "webhook", "webhook_path": "x"},
                        },
                        {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
                    ],
                    "edges": [{"from_": "in", "to": "out"}],
                },
            },
        )
        req = _FakeRequest(b"{}", "wrong-token")
        with pytest.raises(HTTPException) as exc_info:
            await workflow_webhook(wf.id, "x", req, session)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_webhook_plain_text_payload(async_session_factory, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "workflow_webhook_shared_token", "test-token")

    async with async_session_factory() as session:
        org = Organization(name="Webhook Corp3", slug="webhook-corp3")
        session.add(org)
        await session.flush()
        wf = await WorkflowService(session).create(
            org.id,
            {
                "name": "Hook3",
                "description": "",
                "graph": {
                    "nodes": [
                        {
                            "id": "in",
                            "kind": "integration",
                            "parameters": {"source": "webhook", "webhook_path": "x"},
                        },
                        {"id": "out", "kind": "output", "parameters": {"include": "all_inputs"}},
                    ],
                    "edges": [{"from_": "in", "to": "out"}],
                },
            },
        )
        req = _FakeRequest(b"plain text body", "test-token")
        result = await workflow_webhook(wf.id, "x", req, session)
        run = await session.scalar(
            select(WorkflowRun).where(WorkflowRun.id == result["workflow_run_id"])
        )
        assert run.input["webhook_payload"] == "plain text body"
