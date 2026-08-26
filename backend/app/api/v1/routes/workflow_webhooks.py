"""Workflow webhook endpoint.

``POST /api/webhooks/workflow/{workflow_id}/{path}`` lets an integration node
with source ``webhook`` fire the workflow with an external payload. The route is
unauthenticated (webhooks can't send cookies) but requires a shared token in the
``X-Webhook-Token`` header, mirroring the gmail webhook auth pattern.
"""

from __future__ import annotations

import asyncio
import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import gen_id
from app.db.session import get_db
from app.models.outbox import OutboxEvent
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun

router = APIRouter(prefix="/api/webhooks/workflow", tags=["webhooks"])

_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1MB


def _verify_token(request: Request) -> None:
    settings = get_settings()
    expected = settings.workflow_webhook_shared_token
    if not expected:
        raise HTTPException(503, "workflow webhooks are not configured")
    supplied = request.headers.get("x-webhook-token", "")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "invalid webhook token")


@router.post("/{workflow_id}/{path:path}")
async def workflow_webhook(
    workflow_id: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fire a workflow with the request body as its webhook payload."""
    _verify_token(request)

    workflow = await db.scalar(select(Workflow).where(Workflow.id == workflow_id))
    if workflow is None:
        raise HTTPException(404, "workflow not found")

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_BYTES:
        raise HTTPException(413, "payload too large")
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        raise HTTPException(413, "payload too large")

    try:
        payload = body.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "payload must be UTF-8 text or JSON") from None
    try:
        import json

        parsed_payload: Any = json.loads(payload)
    except json.JSONDecodeError:
        parsed_payload = payload

    occurrence_id = gen_id()
    run_id = gen_id()
    db.add(
        WorkflowRun(
            id=run_id,
            org_id=workflow.org_id,
            workflow_id=workflow.id,
            status="queued",
            input={
                "text": "",
                "timezone": "UTC",
                "trigger": "webhook",
                "webhook_payload": parsed_payload,
                "path": path,
            },
            triggered_by_user_id=workflow.created_by_user_id,
        )
    )
    await db.flush()
    db.add(
        OutboxEvent(
            event_type="workflow.run.requested",
            aggregate_type="workflow_webhook",
            aggregate_id=occurrence_id,
            org_id=workflow.org_id,
            user_id=workflow.created_by_user_id,
            correlation_id=occurrence_id,
            payload={"run_id": run_id},
            dedupe_key=f"webhook:{occurrence_id}",
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "webhook run could not be queued") from exc
    return {"workflow_run_id": run_id, "status": "queued", "accepted": True}
