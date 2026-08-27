from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from simpleeval import simple_eval
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.guardrails.approval import request_approval
from app.core.guardrails.budget import BudgetTracker, RunBudget
from app.core.observability import genai
from app.core.observability.llm_trace import ObservabilityContext, build_trace_context
from app.core.observability.metrics import workflow_run_duration_seconds
from app.core.providers.factory import build_driver
from app.core.tools.registry import BUILTIN_TOOLS, execute_tool_call
from app.core.tools.types import ToolContext
from app.core.workflow import resume
from app.core.workflow.replay import ReplayCursor, record_tool_call
from app.db.base import utc_now
from app.mcp.client import build_mcp_tool_spec
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow import NodeOutput


def _eval_condition(cond: str, output: Any) -> bool:
    """Evaluate an edge condition against a node's output.

    ``output`` may be a ``NodeOutput`` (or dict) — structured keys like
    ``output.category`` resolve against ``data``; string comparisons fall back
    to ``text``. A plain string keeps the legacy behavior.
    """
    if isinstance(output, NodeOutput):
        data = output.data or {}
        text = output.text
    elif isinstance(output, dict):
        data = output.get("data", {}) or {}
        text = output.get("text", "") or ""
    else:
        data = {}
        text = str(output)
    names: dict[str, Any] = {
        # Legacy conditions read `output` as the text; structured conditions
        # read `output.category` via the data-bound names below. When a node
        # produced no structured data, `output` is the text so old string
        # conditions keep working.
        "output": data if data else text,
        "output_text": text,
        "output_data": data,
    }
    # Bind structured fields: output.category, output.foo...
    for key, value in (data or {}).items():
        if isinstance(key, str) and key.isidentifier():
            names[f"output_{key}"] = value
    try:
        return bool(simple_eval(cond, names=names, functions={"contains": lambda s, sub: sub in str(s)}))
    except Exception:  # noqa: BLE001
        return False


def _get_path(data: dict[str, Any] | None, path: str) -> Any:
    """Resolve a dot path (``emails.0.subject``) into nested data."""
    if not data or not path:
        return None
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def resolve_inputs(
    node: dict[str, Any], outputs: dict[str, NodeOutput], active_upstream: list[str]
) -> dict[str, Any]:
    """Resolve a node's ``input_mapping`` into a ``{field: value}`` dict.

    Falls back to concatenating active upstream ``text`` when no mapping is set.
    The special ``__text__`` key is the assembled prompt/input text.
    """
    cfg = node.get("parameters") or node.get("config") or {}
    mapping = cfg.get("input_mapping") or []
    upstream_text = "\n\n".join(outputs[nid].text for nid in active_upstream if nid in outputs)
    if not mapping:
        return {"__text__": upstream_text}
    mapped: dict[str, Any] = {}
    for item in mapping:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        src = item.get("source_node_id")
        path = item.get("source_path") or ""
        if not field or not src or src not in outputs:
            continue
        value = _get_path(outputs[src].data, path)
        if value is None:
            value = outputs[src].text
        mapped[field] = value
    mapped["__text__"] = upstream_text if not mapped else "\n\n".join(str(v) for v in mapped.values())
    return mapped


def _runtime_agent(agent: Agent) -> Agent:
    """Build a detached runtime agent without copying SQLAlchemy state."""
    return Agent(
        id=agent.id,
        org_id=agent.org_id,
        created_by_user_id=agent.created_by_user_id,
        name=agent.name,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model_id=agent.model_id,
        tools=list(agent.tools or []),
        allowed_risk_tiers=list(agent.allowed_risk_tiers or []),
        kind=agent.kind,
        max_iterations=agent.max_iterations,
        temperature=agent.temperature,
        enable_thinking=agent.enable_thinking,
        active_release_id=agent.active_release_id,
        latest_release_number=agent.latest_release_number,
        auto_rollback_enabled=agent.auto_rollback_enabled,
        auto_rollback_min_pass_rate=agent.auto_rollback_min_pass_rate,
        auto_rollback_cooldown_minutes=agent.auto_rollback_cooldown_minutes,
        a2a_exposed=agent.a2a_exposed,
    )


async def _run_agent_node(
    node: dict[str, Any],
    cfg: dict[str, Any],
    node_run: WorkflowNodeRun,
    upstream_text: str,
    db: AsyncSession,
    actor_user_id: str | None,
) -> NodeOutput:
    """Execute an agent node in dual mode (custom inline or inherit+override).

    Custom mode builds an ephemeral, in-memory ``Agent`` (never persisted).
    Inherit mode loads the org's agent and applies per-field overrides onto a
    shallow copy before running the loop.
    """
    from app.core.agent_loop import run_agent_loop

    mode = cfg.get("mode")
    agent: Agent | None = None
    system_prompt = ""
    model_id = cfg.get("model_id")
    tools: list[str] | None = None
    temperature: float | None = None
    max_iterations: int | None = None
    enable_thinking: bool | None = None

    if mode == "inherit" or (mode is None and node.get("agent_id")):
        agent_id = cfg.get("agent_id") or node.get("agent_id")
        if not agent_id:
            raise RuntimeError("agent node (inherit mode) requires an agent")
        res = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.org_id == node.get("_org_id", "")))
        agent = res.scalar_one_or_none()
        if agent is None:
            raise RuntimeError(f"agent '{agent_id}' not found")
        agent = _runtime_agent(agent)
        system_prompt = cfg.get("system_prompt_override") or agent.system_prompt or ""
        model_id = cfg.get("model_id_override") or model_id
        if "tools_override" in cfg:
            tools = cfg["tools_override"]
        if "temperature_override" in cfg:
            temperature = float(cfg["temperature_override"])
        if "max_iterations_override" in cfg:
            max_iterations = int(cfg["max_iterations_override"])
        if "enable_thinking_override" in cfg:
            enable_thinking = bool(cfg["enable_thinking_override"])
    elif mode is None:
        # Legacy node (no mode, no agent_id): fall back to the org's first
        # agent; if none exists, synthesize a passthrough result (old behavior).
        res = await db.execute(
            select(Agent)
            .where(Agent.org_id == node.get("_org_id", ""))
            .order_by(Agent.created_at.asc())
            .limit(1)
        )
        agent = res.scalar_one_or_none()
        if agent is None:
            text = upstream_text or "Task processed."
            return NodeOutput(
                text=f"[{node.get('label', 'Agent')}] Completed synthesis:\n{text[:600]}",
                data={"synthesized": True},
            )
        agent = _runtime_agent(agent)
        system_prompt = agent.system_prompt or ""
        model_id = agent.model_id
    else:
        # custom mode (default)
        system_prompt = str(cfg.get("system_prompt") or "You are a helpful workflow agent.")
        model_id = cfg.get("model_id")
        if not model_id:
            raise RuntimeError("custom agent node requires a model")
        tools = cfg.get("tools")
        temperature = cfg.get("temperature")
        max_iterations = cfg.get("max_iterations")
        enable_thinking = cfg.get("enable_thinking")

    if agent is None:
        agent = Agent(
            org_id=node.get("_org_id", ""),
            name=f"workflow-node-{node.get('id', 'agent')}",
            system_prompt=system_prompt,
            model_id=model_id,
            tools=tools or [],
            temperature=temperature if temperature is not None else 0.7,
            max_iterations=int(max_iterations or 12),
            enable_thinking=enable_thinking,
        )
    else:
        # apply overrides onto the (copied) agent
        if system_prompt:
            agent.system_prompt = system_prompt
        if model_id:
            agent.model_id = model_id
        if tools is not None:
            agent.tools = tools
        if temperature is not None:
            agent.temperature = temperature
        if max_iterations is not None:
            agent.max_iterations = max_iterations
        if enable_thinking is not None:
            agent.enable_thinking = enable_thinking

    text = upstream_text or "Process workflow automation step."
    loop = await run_agent_loop(
        agent,
        text,
        db,
        depth=0,
        root_run_id=node.get("_run_id"),
        user_id=actor_user_id,
        model_id=model_id,
    )
    data: dict[str, Any] = {"content": loop.content}
    usage = getattr(loop, "usage", None) or getattr(loop, "token_usage", None)
    if usage:
        data["usage"] = usage
    cost = getattr(loop, "cost_usd", None)
    if cost is not None:
        data["cost_usd"] = cost
    latency = getattr(loop, "latency_ms", None)
    if latency is not None:
        data["latency_ms"] = latency
    tool_calls = getattr(loop, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = tool_calls
    return NodeOutput(text=loop.content, data=data)


async def _run_triager(
    node: dict[str, Any], cfg: dict[str, Any], upstream_text: str, db: AsyncSession
) -> NodeOutput:
    """Route/classify upstream data via LLM or rules."""
    mode = cfg.get("mode")
    categories = str(cfg.get("categories") or "high_priority, action_required, routine")
    category_list = [c.strip() for c in re.split(r"[,;\n]", categories) if c.strip()]

    if mode is None:
        # Legacy placeholder node (no mode): keep the old passthrough text so
        # existing graphs still run without an LLM/connection.
        policy = cfg.get("policy") or cfg.get("rules") or "urgency_and_intent"
        return NodeOutput(
            text=(
                f"Triage routed under policy [{policy}] (categories: {category_list}):\n"
                f"{upstream_text or 'No raw items to triage; passing trigger signal.'}"
            ),
            data={"category": "", "reason": f"legacy policy {policy}"},
        )

    if mode == "rules":
        rules = cfg.get("rules") or []
        if isinstance(rules, dict):
            rules = list(rules.values())
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            pattern = rule.get("pattern")
            category = rule.get("category")
            if not pattern or not category:
                continue
            try:
                if re.search(str(pattern), upstream_text, re.IGNORECASE):
                    return NodeOutput(text=category, data={"category": category, "reason": f"rule match: {pattern}"})
            except re.error:
                continue
        return NodeOutput(text="", data={"category": "", "reason": "no rule matched"})

    # LLM mode
    model_id = cfg.get("model_id")
    org_id = node.get("_org_id", "")
    instruction = str(cfg.get("instruction") or "")
    output_format = cfg.get("output_format", "category_with_reason")
    result, _usage, _calls = await _llm_classify(
        db, org_id, model_id, upstream_text, category_list, instruction
    )
    try:
        parsed = json.loads(result)
        category = str(parsed.get("category") or "").strip()
        reason = str(parsed.get("reason") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        category = result.strip()[:80]
        reason = ""
    if not category:
        category = category_list[0] if category_list else "unclassified"
    text = category if output_format == "category_only" else f"{category} — {reason}".strip(" —")
    return NodeOutput(text=category, data={"category": category, "reason": reason})


async def _llm_classify(
    db: AsyncSession,
    org_id: str,
    model_id: str | None,
    text: str,
    categories: list[str],
    instruction: str,
) -> tuple[str, dict, list]:
    """Call the org's model to classify text into one of ``categories``."""
    from app.models.model import Model
    from app.models.provider import Provider

    settings = get_settings()
    if model_id:
        res = await db.execute(select(Model).where(Model.id == model_id, Model.org_id == org_id))
        model = res.scalar_one_or_none()
    else:
        res = await db.execute(
            select(Model).where(Model.org_id == org_id, Model.enabled.is_(True)).order_by(Model.created_at.asc()).limit(1)
        )
        model = res.scalar_one_or_none()
    if model is None:
        raise RuntimeError("no model available for triager LLM routing")
    res = await db.execute(select(Provider).where(Provider.id == model.provider_id))
    provider = res.scalar_one_or_none()
    if provider is None:
        raise RuntimeError("provider not found for triager model")
    observability = (
        ObservabilityContext(
            build_trace_context(
                trace_id=f"workflow-triager-{node_id()}",
                session_id=None,
                org_id=org_id,
                metadata={"run_type": "workflow_triager"},
            )
        )
        if settings.observability_enabled
        else None
    )
    llm = build_driver(provider, model, observability=observability, generation_name="workflow-triager")
    category_prompt = ", ".join(categories)
    system = (
        "You are a workflow router. Classify the input into EXACTLY one of these "
        f"categories: {category_prompt}.\n{instruction}\n"
        'Respond with ONLY a JSON object: {"category": "...", "reason": "..."}'
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": text[:12000]}]
    content, _usage, _tool_calls = await llm.complete(messages, temperature=0.2)
    return content, _usage, _tool_calls or []


def node_id() -> str:
    from app.db.base import gen_id

    return gen_id()


async def _run_integration(
    node: dict[str, Any], cfg: dict[str, Any], upstream_text: str, db: AsyncSession
) -> NodeOutput:
    """Fetch real data from Gmail / Google Calendar / Google Drive / webhook.

    Reuses the customer-intelligence connector stack (OAuth credentials +
    MCP providers). Missing connection => clear error, never mock data.
    """
    source = str(cfg.get("source") or "system").lower()
    # normalize legacy spellings from LLM-generated graphs / old templates
    if source in {"google_calendar", "calendar"}:
        source = "google_calendar"
    elif source in {"google_drive", "drive"}:
        source = "google_drive"
    operation = str(cfg.get("operation") or "list_new")
    max_results = int(cfg.get("max_results") or 20)
    org_id = node.get("_org_id", "")
    user_id = node.get("_user_id")

    if source == "webhook":
        payload = node.get("_webhook_payload") or {}
        return NodeOutput(
            text=str(payload)[:2000],
            data={"webhook": payload},
        )

    if not user_id:
        raise RuntimeError("integration node requires a user context for connection access")

    try:
        if source == "gmail":
            return await _integration_gmail(db, org_id, user_id, operation, max_results, cfg)
        if source == "google_calendar":
            return await _integration_calendar(db, org_id, user_id, max_results, cfg)
        if source == "google_drive":
            return await _integration_drive(db, org_id, user_id, max_results, cfg)
        if source in {"gmail_and_calendar", "gmail_calendar"}:
            gmail_out = await _integration_gmail(db, org_id, user_id, operation, max_results, cfg)
            cal_out = await _integration_calendar(db, org_id, user_id, max_results, cfg)
            return NodeOutput(
                text=f"{gmail_out.text}\n\n{cal_out.text}",
                data={"emails": gmail_out.data.get("emails", []), "events": cal_out.data.get("events", [])},
            )
        raise RuntimeError(f"unknown integration source: {source}")
    except ValueError as exc:
        raise RuntimeError(f"integration node ({source}): {exc}") from exc


async def _integration_gmail(
    db: AsyncSession, org_id: str, user_id: str, operation: str, max_results: int, cfg: dict
) -> NodeOutput:
    from app.customer_intelligence.oauth import load_fresh_credentials
    from app.customer_intelligence.providers.email import bind_email_provider, get_email_provider
    from app.repositories.customer_intelligence import EmailConnectionRepository

    conn_repo = EmailConnectionRepository(db)
    conns = await conn_repo.list(org_id)
    conn = next(
        (c for c in conns if c.status == "connected" and c.provider == "gmail" and c.created_by_user_id == user_id),
        None,
    )
    if conn is None or not getattr(conn, "credentials_enc", None):
        raise ValueError("no connected Gmail account; connect one in Settings")
    creds = await load_fresh_credentials(db, conn)
    provider = bind_email_provider(get_email_provider(conn.provider), creds)

    emails: list[dict[str, Any]] = []
    if operation == "get":
        msg_id = cfg.get("message_id") or cfg.get("query")
        if not msg_id:
            raise ValueError("'get' operation requires a message id")
        msg = await provider.get_message(msg_id)
        emails = [
            {
                "id": getattr(msg, "provider_message_id", msg_id),
                "from": getattr(msg, "sender_email", ""),
                "subject": getattr(msg, "subject", ""),
                "snippet": (getattr(msg, "body_text", "") or "")[:500],
            }
        ]
    elif operation == "search":
        query = cfg.get("query") or ""
        results = await provider.search(query=query, max_results=max_results)
        emails = [
            {
                "id": getattr(m, "provider_message_id", ""),
                "from": getattr(m, "sender_email", ""),
                "subject": getattr(m, "subject", ""),
                "snippet": (getattr(m, "body_text", "") or "")[:500],
            }
            for m in (results or [])
        ]
    else:
        page = await provider.list_new(cursor=None, max_results=max_results)
        emails = _emails_from_page(page)

    lines = [
        f"- From: {e['from']} | Subject: {e['subject']} | {e['snippet'][:80]}"
        for e in emails[:max_results]
    ]
    text = "\n".join(lines) if lines else "No email found."
    return NodeOutput(text=text, data={"emails": emails[:max_results]})


def _emails_from_page(page: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in getattr(page, "messages", []) or []:
        out.append(
            {
                "id": getattr(m, "provider_message_id", ""),
                "from": getattr(m, "sender_email", ""),
                "subject": getattr(m, "subject", ""),
                "snippet": (getattr(m, "body_text", "") or "")[:500],
            }
        )
    return out


async def _integration_calendar(
    db: AsyncSession, org_id: str, user_id: str, max_results: int, cfg: dict
) -> NodeOutput:
    from app.customer_intelligence.oauth import load_fresh_credentials
    from app.customer_intelligence.providers.research import (
        bind_calendar_provider,
        get_calendar_provider,
    )
    from app.repositories.customer_intelligence import CalendarConnectionRepository

    conn = await CalendarConnectionRepository(db).get_connected(org_id, user_id)
    if conn is None or not getattr(conn, "credentials_enc", None):
        raise ValueError("no connected Google Calendar account; connect one in Settings")
    creds = await load_fresh_credentials(db, conn)
    provider = bind_calendar_provider(get_calendar_provider(), creds)

    from datetime import datetime, timedelta
    from datetime import timezone as dt_timezone

    now = datetime.now(dt_timezone.utc)
    time_range = cfg.get("time_range", "7d")
    days = {"today": 1, "7d": 7, "30d": 30}.get(str(time_range), 7)
    events = await provider.list_events(from_=now, to=now + timedelta(days=days), max_results=max_results)
    rows = [
        {
            "title": getattr(e, "title", "") or getattr(e, "summary", ""),
            "start_at": getattr(e, "start_at", None),
            "end_at": getattr(e, "end_at", None),
            "attendees": getattr(e, "attendees", []) or [],
        }
        for e in (events or [])
    ]
    # Serialize datetimes to ISO strings for JSON persistence
    for row in rows:
        for key in ("start_at", "end_at"):
            value = row.get(key)
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()
    lines = [
        f"- {r['title']} @ {r['start_at']} ({len(r['attendees'])} attendees)"
        for r in rows
    ]
    text = "\n".join(lines) if lines else "No upcoming events found."
    return NodeOutput(text=text, data={"events": rows})


async def _integration_drive(
    db: AsyncSession, org_id: str, user_id: str, max_results: int, cfg: dict
) -> NodeOutput:
    from app.customer_intelligence.oauth import load_fresh_credentials
    from app.customer_intelligence.providers.drive import McpDriveProvider
    from app.repositories.customer_intelligence import DriveConnectionRepository

    conn = await DriveConnectionRepository(db).get_connected(org_id, user_id)
    if conn is None or not getattr(conn, "credentials_enc", None):
        raise ValueError("no connected Google Drive account; connect one in Settings")
    creds = await load_fresh_credentials(db, conn)
    provider = McpDriveProvider(creds)

    files = await provider.list_files(page_size=max_results)
    rows = [
        {
            "name": f.get("name", "") if isinstance(f, dict) else getattr(f, "name", ""),
            "id": f.get("id", "") if isinstance(f, dict) else getattr(f, "id", ""),
            "mime_type": f.get("mimeType", "") if isinstance(f, dict) else getattr(f, "mime_type", ""),
            "modified": f.get("modifiedTime", None) if isinstance(f, dict) else (getattr(f, "modified_time", None) or getattr(f, "modified", None)),
        }
        for f in (files or [])
    ]
    lines = [f"- {r['name']} ({r['mime_type']})" for r in rows]
    text = "\n".join(lines) if lines else "No files found."
    return NodeOutput(text=text, data={"files": rows})


class WorkflowWaitingApproval(RuntimeError):
    def __init__(self, approval_id: str) -> None:
        super().__init__("workflow waiting for approval")
        self.approval_id = approval_id


async def create_workflow_run(
    workflow: Any,
    input_text: str,
    db: AsyncSession,
    workflow_run_id: str | None = None,
    user_id: str | None = None,
    timezone_name: str | None = None,
) -> WorkflowRun:
    if workflow_run_id:
        res = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == workflow_run_id,
                WorkflowRun.org_id == workflow.org_id,
                WorkflowRun.workflow_id == workflow.id,
            )
        )
        existing = res.scalar_one_or_none()
        if existing is not None:
            return existing
        raise ValueError("workflow run not found")
    run = WorkflowRun(
        org_id=workflow.org_id,
        workflow_id=workflow.id,
        status="running",
        input={"text": input_text, "timezone": timezone_name},
        triggered_by_user_id=user_id or workflow.created_by_user_id,
        started_at=utc_now(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def _start_node_run(
    db: AsyncSession,
    workflow_run_id: str,
    node_id: str,
    attempt: int,
    node_input: dict[str, Any],
) -> WorkflowNodeRun:
    node_run = WorkflowNodeRun(
        workflow_run_id=workflow_run_id,
        node_id=node_id,
        attempt=attempt,
        status="running",
        input=node_input,
        started_at=utc_now(),
    )
    db.add(node_run)
    await db.commit()
    await db.refresh(node_run)
    return node_run


async def _finish_node_run(
    db: AsyncSession,
    node_run: WorkflowNodeRun,
    *,
    status: str,
    output: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    node_run.status = status
    node_run.output = output or {}
    node_run.error = error
    node_run.finished_at = utc_now()
    await db.commit()


async def _run_workflow_events(
    workflow: Any,
    input_text: str,
    db: AsyncSession,
    workflow_run_id: str | None = None,
    force_inline: bool = False,
    replay_of_run_id: str | None = None,
    user_id: str | None = None,
    timezone_name: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    settings = get_settings()
    workflow_run = await create_workflow_run(
        workflow, input_text, db, workflow_run_id, user_id, timezone_name
    )
    timezone_name = (workflow_run.input or {}).get("timezone") or timezone_name
    actor_user_id = workflow_run.triggered_by_user_id or user_id or workflow.created_by_user_id
    workflow_observability = (
        ObservabilityContext(
            build_trace_context(
                trace_id=workflow_run.id,
                session_id=None,
                org_id=workflow.org_id,
                user_id=actor_user_id,
                metadata={"run_type": "workflow", "workflow_id": workflow.id},
            )
        )
        if settings.observability_enabled
        else None
    )
    yield {
        "event": "workflow_start",
        "data": {
            "workflow_run_id": workflow_run.id,
            "workflow_id": workflow.id,
            "status": workflow_run.status,
        },
    }

    # Queued execution is deliberately detached from this HTTP/SSE request.
    # The worker owns the durable run; the client can poll/reconnect later.
    if settings.workflow_execution_mode == "queued" and not force_inline:
        from app.core.workflow.queue import enqueue_workflow_run

        if workflow_run.status not in {"queued", "running"} or workflow_run_id is None:
            await enqueue_workflow_run(workflow_run.id)
            workflow_run.status = "queued"
            await db.commit()
            yield {"event": "workflow_queued", "data": {"workflow_run_id": workflow_run.id}}
        else:
            yield {"event": "workflow_attached", "data": {"workflow_run_id": workflow_run.id}}
        return

    # An inline reconnect may race with the original request or a worker.
    # Claiming the DB lease prevents two executors from running side effects.
    if workflow_run_id and workflow_run.status in {"succeeded", "failed", "diverged"}:
        yield {
            "event": "workflow_finished",
            "data": {"workflow_run_id": workflow_run.id, "status": workflow_run.status},
        }
        return
    if not await resume.acquire_lease(db, workflow_run.id):
        yield {
            "event": "workflow_busy",
            "data": {"workflow_run_id": workflow_run.id, "status": workflow_run.status},
        }
        return
    workflow_run.status = "running"
    await db.commit()

    # Position of the next recorded tool call; replay lines up against it.
    tool_sequence = 0
    replay_cursor: ReplayCursor | None = None
    if replay_of_run_id:
        replay_cursor = await ReplayCursor.load(
            db, org_id=workflow.org_id, workflow_run_id=replay_of_run_id
        )
        workflow_run.replay_of_run_id = replay_of_run_id
        await db.commit()
        yield {
            "event": "replay_start",
            "data": {"source_run_id": replay_of_run_id, "recorded_calls": len(replay_cursor)},
        }

    graph = workflow.graph or {}
    nodes = graph.get("nodes", [])
    edges = [{**edge, "_idx": idx} for idx, edge in enumerate(graph.get("edges", []))]
    if not nodes:
        workflow_run.status = "failed"
        workflow_run.error = "workflow has no nodes"
        workflow_run.finished_at = utc_now()
        await db.commit()
        await resume.release_lease(db, workflow_run.id)
        yield {"event": "error", "data": {"message": "workflow has no nodes"}}
        return

    node_by_id = {n["id"]: n for n in nodes}
    edges_from: dict[str, list[dict[str, Any]]] = {n["id"]: [] for n in nodes}
    edges_to: dict[str, list[dict[str, Any]]] = {n["id"]: [] for n in nodes}
    for e in edges:
        edges_from.setdefault(e["from_"], []).append(e)
        edges_to.setdefault(e["to"], []).append(e)

    input_nodes = [n for n in nodes if n.get("kind") in ("input", "scheduler", "integration")]
    if len(input_nodes) < 1:
        workflow_run.status = "failed"
        workflow_run.error = (
            "workflow must have at least one entry trigger node (input or scheduler)"
        )
        workflow_run.finished_at = utc_now()
        await db.commit()
        await resume.release_lease(db, workflow_run.id)
        yield {
            "event": "error",
            "data": {
                "message": "workflow must have at least one entry trigger node (input or scheduler)"
            },
        }
        return

    status: dict[str, str] = {n["id"]: "pending" for n in nodes}
    outputs: dict[str, str] = {}
    active_edges: set[int] = set()
    # Populated only when re-entering an existing run (crash recovery); empty
    # for a fresh run, so the normal path is unaffected.
    resumed_outputs: dict[str, str] = (
        await resume.completed_node_outputs(db, workflow_run.id) if workflow_run_id else {}
    )
    # Rebuild the in-memory scheduler from durable node checkpoints. Without
    # this, a reconnect knows the outputs but still treats every node as
    # pending and cannot make downstream nodes ready.
    for node in nodes:
        node_id = node["id"]
        if node_id in resumed_outputs:
            status[node_id] = "done"
            raw = resumed_outputs[node_id]
            if isinstance(raw, dict):
                outputs[node_id] = NodeOutput(text=str(raw.get("text", "")), data=raw.get("data") or {})
            else:
                outputs[node_id] = NodeOutput(text=str(raw))
    for node in nodes:
        if status[node["id"]] != "done":
            continue
        for edge in edges_from[node["id"]]:
            if edge.get("condition") is None or _eval_condition(
                edge["condition"], outputs.get(node["id"], "")
            ):
                active_edges.add(edge["_idx"])
    if resumed_outputs:
        yield {
            "event": "workflow_resumed",
            "data": {
                "workflow_run_id": workflow_run.id,
                "completed_nodes": sorted(resumed_outputs),
            },
        }
    budget = BudgetTracker(
        RunBudget(
            max_tool_calls=settings.budget_max_tool_calls,
            max_cost_usd=settings.budget_max_cost_usd,
            max_wall_seconds=settings.budget_max_wall_seconds,
            max_repeated_call=settings.budget_max_repeated_call,
        )
    )

    async def run_node_once(
        node: dict[str, Any], node_run: WorkflowNodeRun, db: AsyncSession
    ) -> NodeOutput:
        kind = node.get("kind") or node.get("type")
        cfg = node.get("parameters") or node.get("config") or {}
        incoming = [e for e in edges_to[node["id"]] if e["_idx"] in active_edges]
        active_upstream = [e["from_"] for e in incoming]
        resolved = resolve_inputs(node, outputs, active_upstream)
        upstream_text = str(resolved.get("__text__", "")) or input_text

        if kind == "input":
            return NodeOutput(text=input_text or "Input initialized.", data={"input": input_text})
        if kind == "scheduler":
            cron = cfg.get("cron") or cfg.get("schedule") or cfg.get("custom_cron") or "daily"
            label = (
                cfg.get("schedule_label")
                or cfg.get("label")
                or node.get("label")
                or "Scheduler Trigger"
            )
            return NodeOutput(
                text=input_text or f"[{label}] Automated trigger initiated (schedule: {cron}).",
                data={
                    "cron": cron,
                    "timezone": cfg.get("timezone") or timezone_name or "UTC",
                    "schedule_label": label,
                },
            )
        if kind == "triager":
            return await _run_triager(node, cfg, upstream_text, db)
        if kind == "integration":
            return await _run_integration(node, cfg, upstream_text, db)
        if kind == "merge":
            vals = [outputs[e["from_"]].text for e in incoming if e["from_"] in outputs]
            separator = str(cfg.get("separator") or "\n\n")
            if node.get("merge_mode") == "any":
                for v in vals:
                    if v:
                        return NodeOutput(text=v, data={"merged": v})
                return NodeOutput(text="", data={"merged": ""})
            joined = separator.join(vals)
            return NodeOutput(text=joined, data={"merged": joined})
        if kind == "output":
            include = cfg.get("include", "all_inputs")
            if include == "selected":
                selected = cfg.get("selected_from") or []
                parts = [outputs[sid].text for sid in selected if sid in outputs]
            else:
                parts = [outputs[e["from_"]].text for e in incoming if e["from_"] in outputs]
            text = "\n\n".join(p for p in parts if p) or (
                input_text or "Workflow execution completed successfully."
            )
            if cfg.get("format") == "json":
                data = {e["from_"]: outputs[e["from_"]].data for e in incoming if e["from_"] in outputs}
                return NodeOutput(text=text, data=data)
            return NodeOutput(text=text, data={"output": text})
        if kind == "tool":
            tool_name = cfg.get("tool")
            if not tool_name:
                raise RuntimeError("tool node missing 'tool' in config")
            args = dict(cfg.get("arguments") or {})
            # Backward compatibility: legacy tool nodes passed arguments as
            # extra keys on the node config (besides the reserved ones).
            reserved = {"tool", "arguments", "retry", "timeout_s", "onError", "fallback", "input_mapping"}
            for key, value in cfg.items():
                if key not in reserved and key not in args:
                    args[key] = value
            # input_mapping fields override same-named static arguments
            for key, value in resolved.items():
                if key != "__text__":
                    args[key] = value
            spec = BUILTIN_TOOLS.get(tool_name)
            if spec is None:
                spec = await build_mcp_tool_spec(tool_name, db, org_id=workflow.org_id)
            if spec is None:
                raise RuntimeError(f"tool '{tool_name}' not found")
            tool_observation = (
                workflow_observability.start_tool_observation(
                    tool_name=tool_name,
                    tool_call_id=None,
                    arguments=args,
                    metadata={"workflow_node_id": node["id"], "node_run_id": node_run.id},
                )
                if workflow_observability is not None
                else None
            )
            budget_reason = budget.record_call(tool_name, args)
            if budget_reason:
                error = RuntimeError(f"workflow budget exceeded: {budget_reason}")
                if tool_observation is not None:
                    tool_observation.finish_error(error)
                raise error
            if replay_cursor is not None:
                # Replay never executes a tool node. Divergence propagates as
                # an exception so the node is recorded failed rather than the
                # tool quietly firing for real.
                try:
                    replayed = replay_cursor.next_result(tool_name, args)
                except Exception as exc:  # noqa: BLE001
                    if tool_observation is not None:
                        tool_observation.finish_error(exc)
                    raise
                if tool_observation is not None:
                    tool_observation.finish_success(result=replayed)
                return NodeOutput(text=str(replayed), data={"result": replayed})

            ctx = ToolContext(
                db=db,
                depth=0,
                workspace_dir=settings.workspace_dir,
                org_id=workflow.org_id,
                user_id=actor_user_id,
                timezone_name=timezone_name,
            )
            started = time.monotonic()
            try:
                result = await execute_tool_call(spec, args, ctx)
            except asyncio.CancelledError:
                if tool_observation is not None:
                    tool_observation.finish_cancelled()
                raise
            except Exception as exc:
                if tool_observation is not None:
                    tool_observation.finish_error(exc)
                raise
            if tool_observation is not None:
                tool_observation.finish_success(result=result)
            nonlocal tool_sequence
            tool_sequence += 1
            await record_tool_call(
                db,
                org_id=workflow.org_id,
                sequence=tool_sequence,
                tool_name=tool_name,
                arguments=args,
                result=str(result),
                duration_ms=int((time.monotonic() - started) * 1000),
                workflow_run_id=workflow_run.id,
                node_run_id=node_run.id,
                commit=True,
            )
            return NodeOutput(text=str(result), data={"result": result})
        if kind == "approval":
            approval = await request_approval(
                db,
                org_id=workflow.org_id,
                run_type="workflow",
                run_id=workflow_run.id,
                node_id=node["id"],
                tool_name=cfg.get("tool_name"),
                args_snapshot=cfg,
                requested_by=actor_user_id,
            )
            raise WorkflowWaitingApproval(approval.id)
        if kind == "sub_workflow":
            child_workflow_id = cfg.get("workflow_id")
            if not child_workflow_id:
                raise RuntimeError("sub_workflow node missing workflow_id")
            res = await db.execute(
                select(Workflow).where(
                    Workflow.id == child_workflow_id,
                    Workflow.org_id == workflow.org_id,
                )
            )
            child = res.scalar_one_or_none()
            if child is None:
                raise RuntimeError(f"sub_workflow '{child_workflow_id}' not found")
            child_input = upstream_text
            child_output, _child_log, _child_run_id = await run_workflow(
                child,
                child_input,
                db,
                stream=False,
                force_inline=True,
                user_id=actor_user_id,
                timezone_name=timezone_name,
            )
            return NodeOutput(text=str(child_output), data={"output": child_output})
        if kind == "agent":
            return await _run_agent_node(node, cfg, node_run, upstream_text, db, actor_user_id)
        raise RuntimeError(f"unknown node kind {kind}")

    async def run_node(node: dict[str, Any], db: AsyncSession) -> NodeOutput:
        cfg = node.get("parameters") or node.get("config") or {}
        retry_cfg = cfg.get("retry") or node.get("retry") or {}
        if not isinstance(retry_cfg, dict):
            retry_cfg = {}
        max_attempts = max(1, int(retry_cfg.get("max_attempts", 1) or 1))
        backoff_s = max(0.0, float(retry_cfg.get("backoff_s", 0.0) or 0.0))
        timeout_s = node.get("timeout_s") or cfg.get("timeout_s")

        # Resume: a node that already succeeded in an earlier attempt of this
        # run is not executed again — its recorded output is replayed. This
        # makes a crashed multi-hour workflow cheap to restart, and stops
        # side-effecting tool nodes from firing twice.
        if node["id"] in resumed_outputs:
            raw = resumed_outputs[node["id"]]
            if isinstance(raw, dict):
                return NodeOutput(text=str(raw.get("text", "")), data=raw.get("data") or {})
            return NodeOutput(text=str(raw))

        last_error: Exception | None = None
        incoming = [e for e in edges_to[node["id"]] if e["_idx"] in active_edges]
        node_input = {"inputs": {e["from_"]: outputs[e["from_"]].text for e in incoming if e["from_"] in outputs}}
        for attempt in range(1, max_attempts + 1):
            node_run = await _start_node_run(db, workflow_run.id, node["id"], attempt, node_input)
            try:
                with genai.workflow_node_span(
                    org_id=workflow_run.org_id,
                    workflow_run_id=workflow_run.id,
                    node_id=node["id"],
                    node_type=str(node.get("kind") or node.get("type") or "unknown"),
                    workflow_name=getattr(workflow, "name", None),
                    agent_release_id=getattr(node_run, "agent_release_id", None),
                ):
                    coro = run_node_once(node, node_run, db)
                    result = (
                        await asyncio.wait_for(coro, timeout=float(timeout_s))
                        if timeout_s
                        else await coro
                    )
            except WorkflowWaitingApproval as exc:
                await _finish_node_run(
                    db,
                    node_run,
                    status="waiting_approval",
                    output={"approval_id": exc.approval_id},
                )
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await _finish_node_run(db, node_run, status="failed", error=str(exc))
                if attempt < max_attempts and backoff_s:
                    await asyncio.sleep(backoff_s)
                continue
            await _finish_node_run(db, node_run, status="succeeded", output={"text": result.text, "data": result.data})
            return result
        raise RuntimeError(str(last_error) if last_error else "node failed")

    async def run_node_in_new_session(
        node: dict[str, Any], session_factory: async_sessionmaker[AsyncSession]
    ) -> NodeOutput:
        async with session_factory() as node_db:
            return await run_node(node, node_db)

    def is_ready(node: dict[str, Any]) -> bool:
        nid = node["id"]
        if status[nid] != "pending":
            return False
        if node.get("kind") in ("input", "scheduler") or not edges_to[nid]:
            return True
        inc = [e for e in edges_to[nid] if e["_idx"] in active_edges]
        if not inc:
            return False
        if node.get("merge_mode") == "any":
            return any(status[e["from_"]] == "done" for e in inc)
        return all(status[e["from_"]] == "done" for e in inc)

    # Enrich each node dict with execution context for the node implementations.
    for n in nodes:
        n["_org_id"] = workflow.org_id
        n["_user_id"] = actor_user_id
        n["_run_id"] = workflow_run.id
        n["_webhook_payload"] = (workflow_run.input or {}).get("webhook_payload") or {}

    concurrency_limit = max(1, int(getattr(settings, "workflow_max_concurrency", 8) or 8))
    semaphore = asyncio.Semaphore(concurrency_limit)

    async def _run_bounded(
        node: dict[str, Any], db: AsyncSession, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> NodeOutput:
        async with semaphore:
            if session_factory is not None:
                async with session_factory() as node_db:
                    return await run_node(node, node_db)
            return await run_node(node, db)

    error_flag = False
    while True:
        ready = [n for n in nodes if is_ready(n)]
        if not ready:
            pending = [n for n in nodes if status[n["id"]] == "pending"]
            if not pending:
                break
            for n in pending:
                status[n["id"]] = "skipped"
                yield {
                    "event": "node_error",
                    "data": {"node_id": n["id"], "message": "unreachable"},
                }
            break

        tasks: dict[str, asyncio.Task] = {}
        fan_out = len(ready) > 1
        if fan_out:
            # 2+ nodes are ready in the same round (a fan-out). AsyncSession
            # is not safe for concurrent use by multiple coroutines, so each
            # concurrently-dispatched node gets its own session bound to the
            # same engine as `db` — sharing `db` here raises "concurrent
            # operations are not permitted" on whichever node loses the race.
            node_sessionmaker = async_sessionmaker(
                bind=db.bind, class_=AsyncSession, expire_on_commit=False
            )

        for n in ready:
            status[n["id"]] = "running"
            yield {
                "event": "node_start",
                "data": {"node_id": n["id"], "kind": n["kind"]},
            }
            coro = _run_bounded(n, db, node_sessionmaker) if fan_out else _run_bounded(n, db)
            tasks[n["id"]] = asyncio.create_task(coro)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        # Heartbeat between scheduling rounds: a workflow whose nodes take
        # longer than the lease TTL would otherwise look abandoned and get
        # picked up by another worker while it is still running.
        await resume.extend_lease(db, workflow_run.id)
        for nid, res in zip(tasks.keys(), results, strict=False):
            node_def = next((n for n in nodes if n["id"] == nid), None)
            on_error = (node_def.get("parameters") or node_def.get("config") or {}).get("onError", "stop") if node_def else "stop"
            if isinstance(res, WorkflowWaitingApproval):
                status[nid] = "waiting_approval"
                workflow_run.status = "waiting_approval"
                workflow_run.output = {"waiting_node_id": nid, "approval_id": res.approval_id}
                await db.commit()
                yield {
                    "event": "approval_required",
                    "data": {"node_id": nid, "approval_id": res.approval_id},
                }
                await resume.release_lease(db, workflow_run.id)
                return
            if isinstance(res, Exception):
                if on_error == "continue":
                    status[nid] = "skipped"
                    yield {
                        "event": "node_error",
                        "data": {"node_id": nid, "message": str(res), "skipped": True},
                    }
                    for e in edges_from[nid]:
                        active_edges.discard(e["_idx"])
                elif on_error == "fallback":
                    fallback_text = str(
                        (node_def.get("parameters") or node_def.get("config") or {}).get("fallback", "")
                    ) if node_def else ""
                    fallback = NodeOutput(text=fallback_text, data={"fallback": True})
                    status[nid] = "done"
                    outputs[nid] = fallback
                    yield {
                        "event": "node_error",
                        "data": {"node_id": nid, "message": str(res), "fallback": True},
                    }
                    yield {
                        "event": "node_done",
                        "data": {"node_id": nid, "output": fallback_text},
                    }
                    for e in edges_from[nid]:
                        cond = e.get("condition")
                        passed = _eval_condition(cond, fallback) if cond else True
                        if passed:
                            active_edges.add(e["_idx"])
                            yield {
                                "event": "edge",
                                "data": {"from": e["from_"], "to": e["to"]},
                            }
                else:  # stop (default)
                    status[nid] = "error"
                    error_flag = True
                    yield {
                        "event": "node_error",
                        "data": {"node_id": nid, "message": str(res)},
                    }
                    for e in edges_from[nid]:
                        active_edges.discard(e["_idx"])
            else:
                status[nid] = "done"
                outputs[nid] = res
                yield {
                    "event": "node_done",
                    "data": {"node_id": nid, "output": res.text},
                }
                for e in edges_from[nid]:
                    cond = e.get("condition")
                    passed = _eval_condition(cond, res) if cond else True
                    if passed:
                        active_edges.add(e["_idx"])
                        yield {
                            "event": "edge",
                            "data": {"from": e["from_"], "to": e["to"]},
                        }

    out_nodes = [n for n in nodes if n["kind"] == "output"]
    if out_nodes:
        final_output = "\n\n".join(outputs[n["id"]].text for n in out_nodes if n["id"] in outputs)
        final_data = {n["id"]: outputs[n["id"]].data for n in out_nodes if n["id"] in outputs}
    else:
        done = [n for n in nodes if status[n["id"]] == "done"]
        final_output = outputs[done[-1]["id"]].text if done and done[-1]["id"] in outputs else ""
        final_data = {done[-1]["id"]: outputs[done[-1]["id"]].data} if done and done[-1]["id"] in outputs else {}
    yield {
        "event": "done",
        "data": {"output": final_output, "error": error_flag},
    }
    workflow_run.status = "failed" if error_flag else "succeeded"
    workflow_run.output = {"text": final_output, "data": final_data}
    workflow_run.finished_at = utc_now()
    await db.commit()
    await resume.release_lease(db, workflow_run.id)
    workflow_run_duration_seconds.observe(max(0.0, time.monotonic() - budget.started_at))


async def run_workflow_events(
    workflow: Any,
    input_text: str,
    db: AsyncSession,
    workflow_run_id: str | None = None,
    force_inline: bool = False,
    replay_of_run_id: str | None = None,
    user_id: str | None = None,
    timezone_name: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream workflow events and release any executor lease on close."""
    run_id = workflow_run_id
    try:
        async for event in _run_workflow_events(
            workflow,
            input_text,
            db,
            workflow_run_id=workflow_run_id,
            force_inline=force_inline,
            replay_of_run_id=replay_of_run_id,
            user_id=user_id,
            timezone_name=timezone_name,
        ):
            if event.get("event") == "workflow_start":
                run_id = event.get("data", {}).get("workflow_run_id") or run_id
            yield event
    finally:
        # Conditional release is idempotent and only clears this process's
        # lease. This also covers cancellation/client disconnect and errors.
        if run_id is not None:
            await resume.release_lease(db, run_id)


async def run_workflow(
    workflow: Any,
    input_text: str,
    db: AsyncSession,
    stream: bool = False,
    workflow_run_id: str | None = None,
    force_inline: bool = False,
    replay_of_run_id: str | None = None,
    user_id: str | None = None,
    timezone_name: str | None = None,
) -> Any:
    """If stream=True, returns the async generator of events.
    Otherwise awaits and returns (final_output, event_log)."""
    if stream:
        return run_workflow_events(
            workflow,
            input_text,
            db,
            workflow_run_id=workflow_run_id,
            force_inline=force_inline,
            replay_of_run_id=replay_of_run_id,
            user_id=user_id,
            timezone_name=timezone_name,
        )
    final = ""
    log: list[dict[str, Any]] = []
    workflow_run_id_seen = workflow_run_id
    async for ev in run_workflow_events(
        workflow,
        input_text,
        db,
        workflow_run_id=workflow_run_id,
        force_inline=force_inline,
        replay_of_run_id=replay_of_run_id,
        user_id=user_id,
        timezone_name=timezone_name,
    ):
        log.append(ev)
        if ev["event"] == "workflow_start":
            workflow_run_id_seen = ev["data"]["workflow_run_id"]
        if ev["event"] == "done":
            final = ev["data"].get("output", final)
    return final, log, workflow_run_id_seen
