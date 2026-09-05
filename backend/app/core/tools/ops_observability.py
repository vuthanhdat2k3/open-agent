"""Read-only diagnosis tools for the Ops & Reliability agent.

Everything here is safe/read/network risk tier - none of it can mutate
anything besides an OpsFinding row, which is internal bookkeeping, not a
system change. The agent's ability to actually touch the repo lives in
ops_repo.py, gated far more strictly.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.models.approval_request import ApprovalRequest
from app.models.ops_finding import OpsFinding
from app.models.task import Task
from app.models.tool_call_record import ToolCallRecord


async def _query_langfuse_traces(args: dict[str, Any], ctx: ToolContext) -> str:
    from app.config import get_settings

    settings = get_settings()
    if not (settings.langfuse_enabled and settings.langfuse_public_key and settings.langfuse_secret_key):
        return "error: Langfuse is not configured on this deployment"

    level = str(args.get("level") or "ERROR").upper()
    if level not in {"DEBUG", "DEFAULT", "WARNING", "ERROR"}:
        return "error: level must be one of DEBUG, DEFAULT, WARNING, ERROR"
    since_minutes = int(args.get("since_minutes") or 60)
    limit = max(1, min(int(args.get("limit") or 20), 50))

    try:
        from langfuse import Langfuse
        from langfuse.api.commons.types.observation_level import ObservationLevel

        kwargs: dict[str, Any] = {
            "public_key": settings.langfuse_public_key,
            "secret_key": settings.langfuse_secret_key,
        }
        if settings.langfuse_base_url:
            kwargs["base_url"] = settings.langfuse_base_url
        client = Langfuse(**kwargs)
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        result = client.api.observations.get_many(
            level=ObservationLevel(level),
            from_start_time=since,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        return f"error: Langfuse query failed: {exc}"

    rows = []
    for obs in getattr(result, "data", None) or []:
        rows.append(
            {
                "observation_id": getattr(obs, "id", None),
                "trace_id": getattr(obs, "trace_id", None),
                "name": getattr(obs, "name", None),
                "type": getattr(obs, "type", None),
                "level": getattr(obs, "level", None),
                "status_message": getattr(obs, "status_message", None),
                "start_time": str(getattr(obs, "start_time", "")),
                "model": getattr(obs, "model", None),
            }
        )
    if not rows:
        return f"No {level} observations in the last {since_minutes} minutes."
    return json.dumps({"count": len(rows), "observations": rows}, ensure_ascii=False, default=str)


async def _query_system_health(args: dict[str, Any], ctx: ToolContext) -> str:
    if ctx.db is None or not ctx.org_id:
        return "error: missing org context"
    since_minutes = int(args.get("since_minutes") or 60)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=since_minutes)

    failed_by_agent = await ctx.db.execute(
        select(Task.agent_id, func.count(Task.id))
        .where(
            Task.org_id == ctx.org_id,
            Task.status.in_(("failed", "diverged")),
            Task.created_at >= since,
            Task.parent_task_id.is_(None),
        )
        .group_by(Task.agent_id)
    )
    failed_counts = {row[0]: row[1] for row in failed_by_agent.all()}

    approval_by_status = await ctx.db.execute(
        select(ApprovalRequest.status, func.count(ApprovalRequest.id))
        .where(ApprovalRequest.org_id == ctx.org_id, ApprovalRequest.created_at >= since)
        .group_by(ApprovalRequest.status)
    )
    approval_counts = {row[0]: row[1] for row in approval_by_status.all()}

    tool_failures = await ctx.db.execute(
        select(ToolCallRecord.tool_name, func.count(ToolCallRecord.id))
        .where(
            ToolCallRecord.org_id == ctx.org_id,
            ToolCallRecord.status != "ok",
            ToolCallRecord.created_at >= since,
        )
        .group_by(ToolCallRecord.tool_name)
    )
    tool_failure_counts = {row[0]: row[1] for row in tool_failures.all()}

    if not failed_counts and not approval_counts and not tool_failure_counts:
        return f"No task failures, approval activity, or tool failures in the last {since_minutes} minutes."
    return json.dumps(
        {
            "since_minutes": since_minutes,
            "failed_tasks_by_agent": failed_counts,
            "approval_requests_by_status": approval_counts,
            "tool_call_failures_by_tool": tool_failure_counts,
        },
        ensure_ascii=False,
    )


async def _record_ops_finding(args: dict[str, Any], ctx: ToolContext) -> str:
    if ctx.db is None or not ctx.org_id:
        return "error: missing org context"
    title = str(args.get("title") or "").strip()
    if not title:
        return "error: missing 'title'"
    severity = str(args.get("severity") or "info").lower()
    if severity not in {"info", "warning", "error", "critical"}:
        return "error: severity must be one of info, warning, error, critical"

    finding = OpsFinding(
        org_id=ctx.org_id,
        severity=severity,
        title=title,
        summary=str(args.get("summary") or ""),
        evidence=args.get("evidence") or {},
        status="reported",
        related_run_id=ctx.root_run_id,
    )
    ctx.db.add(finding)
    await ctx.db.commit()
    await ctx.db.refresh(finding)
    return f"recorded finding {finding.id}: {title} (severity={severity})"


register(
    ToolSpec(
        name="query_langfuse_traces",
        description=(
            "Query Langfuse for recent LLM generations/tool spans at a given level "
            "(DEBUG, DEFAULT, WARNING, ERROR). Use ERROR to find recent failures. "
            "Provide 'level' (default ERROR), 'since_minutes' (default 60), 'limit' (default 20, max 50)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["DEBUG", "DEFAULT", "WARNING", "ERROR"]},
                "since_minutes": {"type": "number"},
                "limit": {"type": "number"},
            },
        },
        run=_query_langfuse_traces,
        risk_tier=RiskTier.network,
    )
)

register(
    ToolSpec(
        name="query_system_health",
        description=(
            "Query this org's own task/approval/tool-call tables for recent failure signals: "
            "failed root tasks grouped by agent, approval request status distribution, and "
            "tool calls that did not return 'ok', all within the last 'since_minutes' (default 60)."
        ),
        input_schema={
            "type": "object",
            "properties": {"since_minutes": {"type": "number"}},
        },
        run=_query_system_health,
        risk_tier=RiskTier.read,
    )
)

register(
    ToolSpec(
        name="record_ops_finding",
        description=(
            "Record one diagnosis finding for the operator dashboard and delivery channels. "
            "ALWAYS call this once per distinct anomaly you investigate, even low-confidence ones "
            "- do not silently drop a finding. Provide 'title', 'severity' (info|warning|error|critical), "
            "'summary' (plain-text explanation with concrete evidence - trace ids, task ids, error text; "
            "never a vague claim with no evidence), and optional 'evidence' (a JSON object with e.g. "
            "trace_ids/task_ids arrays)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "warning", "error", "critical"]},
                "summary": {"type": "string"},
                "evidence": {"type": "object"},
            },
            "required": ["title", "summary"],
        },
        run=_record_ops_finding,
        risk_tier=RiskTier.safe,
    )
)
