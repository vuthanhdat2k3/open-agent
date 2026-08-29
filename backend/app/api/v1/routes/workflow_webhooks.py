"""Workflow webhook endpoint.

``POST /api/webhooks/workflow/{workflow_id}/{path}`` lets an integration node
with source ``webhook`` fire the workflow with an external payload. The route is
unauthenticated (webhooks can't send cookies) but requires a shared token in the
``X-Webhook-Token`` header, mirroring the gmail webhook auth pattern.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import gen_id, utc_now
from app.db.session import get_db
from app.models.outbox import OutboxEvent
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_run import WorkflowRun

router = APIRouter(prefix="/api/webhooks/workflow", tags=["webhooks"])

_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1MB
_MAX_RUNS_PER_MINUTE = 60


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

    # A paused/archived marketplace installation must not fire, mirroring the
    # scheduler gate. Hand-built workflows (no installation) are unaffected.
    installation_status = await db.scalar(
        select(WorkflowInstallation.status).where(WorkflowInstallation.workflow_id == workflow.id)
    )
    if installation_status is not None and installation_status != "enabled":
        raise HTTPException(409, "workflow is paused")

    # Cheap DoS guard: this endpoint is unauthenticated (token-gated) and each
    # accepted call spends LLM budget, so cap accepted runs per workflow per
    # minute. Idempotency (below) also lets a caller safely retry.
    recent = await db.scalar(
        select(func.count(WorkflowRun.id)).where(
            WorkflowRun.workflow_id == workflow.id,
            WorkflowRun.started_at >= utc_now() - timedelta(minutes=1),
        )
    )
    if (recent or 0) >= _MAX_RUNS_PER_MINUTE:
        raise HTTPException(429, "webhook rate limit exceeded for this workflow")

    webhook_paths = {
        str((node.get("parameters") or node.get("config") or {}).get("webhook_path")).strip("/")
        for node in (workflow.graph or {}).get("nodes", [])
        if isinstance(node, dict)
        and node.get("kind") == "integration"
        and str((node.get("parameters") or node.get("config") or {}).get("source", "")).lower()
        == "webhook"
        and (node.get("parameters") or node.get("config") or {}).get("webhook_path")
    }
    if path.strip("/") not in webhook_paths:
        raise HTTPException(404, "webhook path not found")

    trigger_node = next(
        node
        for node in (workflow.graph or {}).get("nodes", [])
        if isinstance(node, dict)
        and node.get("kind") == "integration"
        and str((node.get("parameters") or node.get("config") or {}).get("source", "")).lower()
        == "webhook"
        and str((node.get("parameters") or node.get("config") or {}).get("webhook_path", "")).strip("/")
        == path.strip("/")
    )
    graph_snapshot = copy.deepcopy(workflow.graph or {})
    graph_hash = hashlib.sha256(
        json.dumps(graph_snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

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
        parsed_payload: Any = json.loads(payload)
    except json.JSONDecodeError:
        parsed_payload = payload

    # Idempotency: a caller that retries (network flake, at-least-once
    # delivery) can pass X-Idempotency-Key; the unique trigger_occurrence_key
    # then collapses duplicates to the first accepted run.
    idem_key = request.headers.get("x-idempotency-key", "").strip()
    occurrence_key = f"webhook:{workflow.id}:{path.strip('/')}:{idem_key}" if idem_key else None
    if occurrence_key:
        existing_run_id = await db.scalar(
            select(WorkflowRun.id).where(WorkflowRun.trigger_occurrence_key == occurrence_key)
        )
        if existing_run_id is not None:
            return {"workflow_run_id": existing_run_id, "status": "queued", "accepted": True, "deduplicated": True}

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
            graph_snapshot=graph_snapshot,
            graph_hash=graph_hash,
            trigger_node_id=trigger_node["id"],
            trigger_type="integration",
            trigger_occurrence_key=occurrence_key,
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
        if occurrence_key:
            raced_run_id = await db.scalar(
                select(WorkflowRun.id).where(WorkflowRun.trigger_occurrence_key == occurrence_key)
            )
            if raced_run_id is not None:
                return {"workflow_run_id": raced_run_id, "status": "queued", "accepted": True, "deduplicated": True}
        raise HTTPException(409, "webhook run could not be queued") from exc
    return {"workflow_run_id": run_id, "status": "queued", "accepted": True}
