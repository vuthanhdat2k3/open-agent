from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import structlog
from simpleeval import simple_eval
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.guardrails.approval import request_approval
from app.core.guardrails.budget import BudgetTracker, RunBudget
from app.core.observability import genai
from app.core.observability.llm_trace import ObservabilityContext, build_trace_context
from app.core.observability.metrics import workflow_run_duration_seconds
from app.core.providers.factory import build_driver
from app.core.tools.authorization import (
    authorize_tool_call,
    build_tool_authorization,
    tool_args_hash,
)
from app.core.tools.authorization import (
    requires_approval as tool_requires_approval,
)
from app.core.tools.registry import BUILTIN_TOOLS, execute_tool_call
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext
from app.core.workflow import resume
from app.core.workflow.replay import ReplayCursor, record_tool_call
from app.db.base import utc_now
from app.models.agent import Agent
from app.models.model import Model
from app.models.approval_request import ApprovalRequest
from app.models.workflow import Workflow
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow import NodeOutput

logger = structlog.get_logger(__name__)

# Sub-workflow nodes recurse through the engine in-process. Graph validation
# only rejects a direct self-reference, so two workflows that reference each
# other (A->B->A) would otherwise recurse until the stack/memory gives out,
# each level spawning runs and LLM calls. Cap the nesting depth.
MAX_SUBWORKFLOW_DEPTH = 3


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
    except Exception as exc:  # noqa: BLE001
        # Surface the failure so an operator can fix a typo'd condition
        # instead of debugging a silent skip in the downstream node. The
        # return-False behavior is preserved on purpose — the existing
        # guardrail test (``test_workflow_condition_rejects_malicious_expression``)
        # depends on it for hostile expressions, and a broken condition
        # should still prevent an unintended branch from firing.
        logger.warning(
            "workflow_edge_condition_failed",
            condition=cond,
            error=str(exc),
            error_type=type(exc).__name__,
        )
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
    actor_user_role: str | None,
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
    model_id = cfg.get("model_id") or node.get("model_id")
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
        system_prompt = cfg.get("system_prompt_override") or cfg.get("system_prompt") or agent.system_prompt or ""
        model_id = cfg.get("model_id_override") or cfg.get("model_id") or node.get("model_id") or model_id
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
        system_prompt = str(cfg.get("system_prompt") or "You are an intelligent workflow agent. Focus on completing your assigned task concisely and accurately based on the provided context. Extract factual, relevant data and do not analyze or audit irrelevant web code, scripts, or HTML markup unless explicitly requested.")
        model_id = cfg.get("model_id")
        if not model_id:
            raise RuntimeError("custom agent node requires a model")
        tools = cfg.get("tools")
        temperature = cfg.get("temperature")
        max_iterations = cfg.get("max_iterations")
        enable_thinking = cfg.get("enable_thinking")

    if db is not None and model_id:
        target_model_stmt = (
            select(Model)
            .where(
                Model.org_id == node.get("_org_id", ""),
                or_(Model.id == model_id, Model.name == model_id),
            )
            .order_by(Model.active.desc())
        )
        target_model = (await db.execute(target_model_stmt)).scalars().first()
        if target_model:
            model_id = target_model.id

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

    upstream = upstream_text or "Process workflow automation step."
    instructions = str(cfg.get("instructions") or "").strip()
    # `instructions` is a common but non-schema field workflow authors (and
    # workflow_generate) use for a per-step task ask, distinct from the
    # agent's own persona in `system_prompt`. Layer it onto the upstream
    # context as the user message rather than overwriting system_prompt, so
    # the underlying agent's tool-use rules/persona still apply.
    text = f"{instructions}\n\n---\nContext from previous step:\n{upstream}" if instructions else upstream
    loop = await run_agent_loop(
        agent,
        text,
        db,
        depth=0,
        root_run_id=node.get("_run_id"),
        user_id=actor_user_id,
        user_role=actor_user_role,
        model_id=model_id,
    )
    if loop.error:
        # A terminal failure inside the agent loop (budget exceeded, provider
        # error, etc.) surfaces here as an empty `content` with `error` set —
        # never as a raised exception. Without this check the node reports
        # "succeeded" with blank output and silently feeds that emptiness to
        # every downstream node instead of stopping/retrying per onError.
        raise RuntimeError(loop.error)
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
    node: dict[str, Any],
    cfg: dict[str, Any],
    upstream_text: str,
    db: AsyncSession,
    *,
    trace_id: str | None = None,
) -> NodeOutput:
    """Route/classify upstream data via LLM or rules."""
    mode = cfg.get("mode")
    categories = str(cfg.get("categories") or "high_priority, action_required, routine")
    category_list = [c.strip() for c in re.split(r"[,;\n]", categories) if c.strip()]
    output_format = cfg.get("output_format", "category_with_reason")

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
                    reason = f"rule match: {pattern}"
                    text = category if output_format == "category_only" else f"{category} — {reason}".strip(" —")
                    return NodeOutput(text=text, data={"category": category, "reason": reason})
            except re.error:
                continue
        return NodeOutput(text="", data={"category": "", "reason": "no rule matched"})

    # LLM mode
    model_id = cfg.get("model_id")
    org_id = node.get("_org_id", "")
    instruction = str(cfg.get("instruction") or "")
    result, _usage, _calls = await _llm_classify(
        db, org_id, model_id, upstream_text, category_list, instruction, trace_id=trace_id
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
    return NodeOutput(text=text, data={"category": category, "reason": reason})


async def _llm_classify(
    db: AsyncSession,
    org_id: str,
    model_id: str | None,
    text: str,
    categories: list[str],
    instruction: str,
    *,
    trace_id: str | None = None,
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
                # Use the parent workflow run's trace id (when known) so this
                # generation lands inside the same Langfuse trace as the rest
                # of the run, instead of appearing as an orphaned trace with
                # no link back to the workflow that triggered it.
                trace_id=trace_id or f"workflow-triager-{node_id()}",
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
    configured_connection_id = cfg.get("connection_id")
    conn = next(
        (
            c
            for c in conns
            if c.status == "connected"
            and c.provider == "gmail"
            and c.created_by_user_id == user_id
            and (not configured_connection_id or c.id == configured_connection_id)
        ),
        None,
    )
    if conn is None or not getattr(conn, "credentials_enc", None):
        raise ValueError("no connected Gmail account; connect one in Settings")
    creds = await load_fresh_credentials(db, conn)
    provider = bind_email_provider(get_email_provider(conn.provider), creds)

    emails: list[dict[str, Any]] = []
    # Gmail durable checkpoint (history_id) captured on a delta fetch and
    # persisted into node_run.output.data["cursor"], so the next run for the
    # same node retrieves only what changed since. ``new_cursor`` from the page
    # is a transient pagination token and must never be stored as the cursor.
    durable_cursor: str | None = None
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
        cursor = cfg.get("_gmail_cursor") or None
        page = await provider.list_new(cursor=cursor, max_results=max_results)
        emails = _emails_from_page(page)
        durable_cursor = getattr(page, "history_id", None) or None

    lines = [
        f"- From: {e['from']} | Subject: {e['subject']} | {e['snippet'][:80]}"
        for e in emails[:max_results]
    ]
    text = "\n".join(lines) if lines else "No email found."
    data: dict[str, Any] = {"emails": emails[:max_results]}
    if durable_cursor:
        data["cursor"] = durable_cursor
    return NodeOutput(text=text, data=data)


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


async def _load_prior_gmail_cursor(db: AsyncSession, current_run_id: str, node_id: str) -> str | None:
    """Return the durable Gmail cursor from the most recent SUCCEEDED execution
    of ``node_id`` in an EARLIER workflow run.

    Each successful delta fetch persists ``data.cursor`` (Gmail ``history_id``)
    on its node_run row; reading the latest one lets the next run continue
    incrementally instead of re-reading the mailbox from the beginning. Runs in
    the same workflow run are excluded so a node never consumes its own output.
    """
    row = (
        await db.execute(
            select(WorkflowNodeRun.output)
            .where(
                WorkflowNodeRun.node_id == node_id,
                WorkflowNodeRun.status == "succeeded",
                WorkflowNodeRun.workflow_run_id != current_run_id,
            )
            .order_by(WorkflowNodeRun.finished_at.desc(), WorkflowNodeRun.attempt.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row or not isinstance(row, dict):
        return None
    data = row.get("data") or {}
    if isinstance(data, dict) and data.get("cursor"):
        return str(data["cursor"])
    return None


async def _integration_calendar(
    db: AsyncSession, org_id: str, user_id: str, max_results: int, cfg: dict
) -> NodeOutput:
    from app.customer_intelligence.oauth import load_fresh_credentials
    from app.customer_intelligence.providers.research import (
        bind_calendar_provider,
        get_calendar_provider,
    )
    from app.repositories.customer_intelligence import CalendarConnectionRepository

    configured_connection_id = cfg.get("connection_id") or cfg.get("calendar_connection_id")
    conn = await CalendarConnectionRepository(db).get_connected(org_id, user_id, connection_id=configured_connection_id)
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


async def _save_output_file(
    workflow: Workflow, cfg: dict[str, Any], text: str, db: AsyncSession, user_id: str | None
) -> None:
    """Persist an output node's final text to the org's Sandbox workspace.

    Reuses the same path-safety + WorkspaceArtifact tracking the `write_file`
    tool uses, so a saved brief shows up on the existing Sandbox page instead
    of needing a new storage mechanism.
    """
    from app.core.tools.paths import safe_resolve
    from app.services.workspace_service import upsert_workspace_artifact

    settings = get_settings()
    raw_name = str(cfg.get("file_name") or "").strip() or f"workflow-outputs/{workflow.id}.md"
    if not raw_name.endswith(".md"):
        raw_name += ".md"
    target = safe_resolve(settings.workspace_dir, raw_name)
    if target is None:
        logger.warning("workflow_output_save_path_escapes_workspace", file_name=raw_name)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    await upsert_workspace_artifact(
        db,
        org_id=workflow.org_id,
        path=target,
        workspace_dir=settings.workspace_dir,
        source_tool="workflow_output",
        user_id=user_id,
    )


async def _deliver_output_to_channel(
    workflow: Workflow, cfg: dict[str, Any], text: str, db: AsyncSession
) -> None:
    """Best-effort delivery of an output node's final text to a connected
    Telegram/Discord channel — lets a scheduled workflow report straight
    into a chat instead of only the Sandbox/notification surfaces.

    Never raises: delivery is a side effect of an already-successful run,
    so a broken channel connection must not fail the node.
    """
    connection_id = cfg.get("channel_connection_id")
    recipient = cfg.get("channel_recipient")
    if not connection_id or not recipient:
        return
    from app.channels.factory import build_channel_driver
    from app.models.channel import ChannelConnection

    res = await db.execute(
        select(ChannelConnection).where(
            ChannelConnection.id == connection_id,
            ChannelConnection.org_id == workflow.org_id,
            ChannelConnection.status == "active",
        )
    )
    connection = res.scalar_one_or_none()
    if connection is None:
        logger.warning(
            "workflow_output_channel_not_found", connection_id=connection_id, workflow_id=workflow.id
        )
        return
    try:
        driver = build_channel_driver(connection)
        await driver.send_message(recipient=str(recipient), content=text)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "workflow_output_channel_delivery_failed",
            error=str(exc),
            connection_id=connection_id,
            workflow_id=workflow.id,
        )


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
    user_role: str | None = None,
    timezone_name: str | None = None,
    trigger_node_id: str | None = None,
    trigger_type: str | None = None,
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
    graph_snapshot = copy.deepcopy(workflow.graph or {})
    graph_nodes = graph_snapshot.get("nodes", []) if isinstance(graph_snapshot, dict) else []
    if trigger_node_id is None:
        trigger_node = next(
            (node for node in graph_nodes if node.get("kind") == "input"), None
        )
        trigger_node_id = trigger_node.get("id") if trigger_node else None
    if trigger_type is None and trigger_node_id:
        trigger_type = next(
            (node.get("kind") for node in graph_nodes if node.get("id") == trigger_node_id),
            None,
        )
    graph_hash = hashlib.sha256(
        json.dumps(graph_snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    run = WorkflowRun(
        org_id=workflow.org_id,
        workflow_id=workflow.id,
        status="running",
        input={"text": input_text, "timezone": timezone_name},
        triggered_by_user_id=user_id or workflow.created_by_user_id,
        started_at=utc_now(),
        graph_snapshot=graph_snapshot,
        graph_hash=graph_hash,
        trigger_node_id=trigger_node_id,
        trigger_type=trigger_type,
        execution_principal={
            "principal_type": "human" if user_id else "system",
            "principal_id": user_id or "openagent:internal-runtime",
            "user_id": user_id,
            "role": user_role,
        },
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


def _reachable_node_ids(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], start: str) -> set[str]:
    """Return the graph slice downstream of one trigger node."""
    outgoing: dict[str, list[str]] = {}
    for edge in edges:
        outgoing.setdefault(str(edge.get("from_")), []).append(str(edge.get("to")))
    reachable: set[str] = set()
    pending = [start]
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(outgoing.get(node_id, []))
    return {node["id"] for node in nodes if node.get("id") in reachable}


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
    user_role: str | None = None,
    timezone_name: str | None = None,
    trigger_node_id: str | None = None,
    trigger_type: str | None = None,
    subworkflow_depth: int = 0,
    parent_trace_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    settings = get_settings()
    workflow_run = await create_workflow_run(
        workflow,
        input_text,
        db,
        workflow_run_id,
        user_id,
        user_role,
        timezone_name,
        trigger_node_id,
        trigger_type,
    )
    timezone_name = (workflow_run.input or {}).get("timezone") or timezone_name
    principal_snapshot = workflow_run.execution_principal or {}
    actor_user_id = (
        principal_snapshot.get("user_id")
        if principal_snapshot
        else workflow_run.triggered_by_user_id or user_id
    ) or workflow.created_by_user_id
    # Never infer the execution role from the person deciding an approval. A
    # missing snapshot on a legacy queued run fails closed at tool execution.
    actor_user_role = principal_snapshot.get("role") if principal_snapshot else None
    workflow_observability = (
        ObservabilityContext(
            build_trace_context(
                # A sub_workflow node passes its parent run's trace id so the
                # child run's generations/tool calls land in the SAME
                # Langfuse trace as the parent, instead of starting an
                # unrelated trace that loses the parent-child relationship.
                trace_id=parent_trace_id or workflow_run.id,
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
            # Persist the queued status BEFORE handing the job to the worker:
            # a worker that claims the job immediately must never observe the
            # pre-commit "running" status and treat this as a live run.
            workflow_run.status = "queued"
            await db.commit()
            await enqueue_workflow_run(workflow_run.id)
            yield {"event": "workflow_queued", "data": {"workflow_run_id": workflow_run.id}}
        else:
            yield {"event": "workflow_attached", "data": {"workflow_run_id": workflow_run.id}}
        return

    # An inline reconnect may race with the original request or a worker.
    # Claiming the DB lease prevents two executors from running side effects.
    if workflow_run_id and workflow_run.status in {"succeeded", "failed", "diverged", "cancelled"}:
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

    graph = workflow_run.graph_snapshot or workflow.graph or {}
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

    active_node_ids = set(node_by_id)
    selected_trigger_id = workflow_run.trigger_node_id
    if selected_trigger_id:
        if selected_trigger_id not in node_by_id:
            workflow_run.status = "failed"
            workflow_run.error = f"trigger node '{selected_trigger_id}' not found in graph snapshot"
            workflow_run.finished_at = utc_now()
            await db.commit()
            await resume.release_lease(db, workflow_run.id)
            yield {"event": "error", "data": {"message": workflow_run.error}}
            return
        active_node_ids = _reachable_node_ids(nodes, edges, selected_trigger_id)
    status: dict[str, str] = {
        n["id"]: ("pending" if n["id"] in active_node_ids else "skipped") for n in nodes
    }
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
                outputs[node_id] = NodeOutput(
                    text=str(raw.get("text", "")),
                    data=raw.get("data") or {},
                )
            else:
                # Legacy / non-dict checkpoint: keep text but never pretend
                # we have structured data. An empty ``data`` means any
                # ``output_data`` / ``output_<key>`` reference in downstream
                # edge conditions will evaluate to None (and fail loudly
                # via the warning in ``_eval_condition``) instead of
                # silently skipping the wrong branches.
                outputs[node_id] = NodeOutput(text=str(raw), data={})
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
            parsed_data = None
            if isinstance(input_text, str) and input_text.strip().startswith(("{", "[")):
                try:
                    parsed_data = json.loads(input_text)
                except Exception:
                    parsed_data = None
            data_payload = parsed_data if isinstance(parsed_data, (dict, list)) else {"input": input_text}
            return NodeOutput(text=input_text or "Input initialized.", data=data_payload)
        if kind == "scheduler":
            cron = cfg.get("cron") or cfg.get("schedule") or cfg.get("custom_cron") or "daily"
            label = (
                cfg.get("schedule_label")
                or cfg.get("label")
                or node.get("label")
                or "Scheduler Trigger"
            )
            trigger_data = {
                "cron": cron,
                "timezone": cfg.get("timezone") or timezone_name or "UTC",
                "schedule_label": label,
            }
            if cfg.get("emit_today_date"):
                from datetime import datetime as _dt
                from zoneinfo import ZoneInfo

                try:
                    tz = ZoneInfo(str(trigger_data["timezone"]))
                except Exception:  # noqa: BLE001
                    tz = ZoneInfo("UTC")
                trigger_data["today_date"] = _dt.now(tz).date().isoformat()
            return NodeOutput(
                text=input_text or f"[{label}] Automated trigger initiated (schedule: {cron}).",
                data=trigger_data,
            )
        if kind == "triager":
            # Reuse the same trace id as the rest of this run (which is
            # already the parent's trace id for a nested sub_workflow), so a
            # triager node never starts an orphaned trace disconnected from
            # its own run's Langfuse trace.
            return await _run_triager(
                node, cfg, upstream_text, db, trace_id=parent_trace_id or workflow_run.id
            )
        if kind == "integration":
            src = str(cfg.get("source") or "").lower()
            if src in {"gmail", "gmail_and_calendar", "gmail_calendar"}:
                cfg = {
                    **cfg,
                    "_gmail_cursor": await _load_prior_gmail_cursor(db, workflow_run.id, node["id"]),
                }
            return await _run_integration(node, cfg, upstream_text, db)
        if kind == "merge":
            vals = [outputs[e["from_"]].text for e in incoming if e["from_"] in outputs]
            separator = str(cfg.get("separator") or "\n\n")
            # merge_mode is normally the generic top-level per-node attribute
            # (see workflow_service.py's graph docstring), but a "merge" kind
            # node's own schema field of the same name lives under
            # `parameters` instead — accept either so a value saved through
            # the node's config form isn't silently ignored.
            if (node.get("merge_mode") or cfg.get("merge_mode")) == "any":
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
            if cfg.get("save_as_file"):
                await _save_output_file(workflow, cfg, text, db, actor_user_id)
            if cfg.get("channel_connection_id"):
                await _deliver_output_to_channel(workflow, cfg, text, db)
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
                from app.mcp.client import build_mcp_tool_spec

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

            authorization = build_tool_authorization(
                org_id=workflow.org_id,
                user_id=actor_user_id,
                user_role=actor_user_role,
                agent_id=None,
                allowed_risk_tiers=[tier.value for tier in RiskTier],
                run_id=workflow_run.id,
                principal_type=(
                    (workflow_run.execution_principal or {}).get("principal_type")
                    or ("human" if actor_user_id and actor_user_role else "system")
                ),
                principal_id=(workflow_run.execution_principal or {}).get("principal_id"),
                replay=replay_cursor is not None,
            )
            # Check capability/RBAC before creating an approval. Approval is
            # only a confirmation gate; it must never grant a principal a risk
            # tier they were not authorized to use in the first place.
            authorize_tool_call(
                spec,
                args,
                context=authorization,
                runtime_org_id=workflow.org_id,
                check_approval=False,
            )
            if tool_requires_approval(spec):
                expected_hash = tool_args_hash(args)
                existing = (
                    await db.execute(
                        select(ApprovalRequest)
                        .where(
                            ApprovalRequest.org_id == workflow.org_id,
                            ApprovalRequest.run_type == "workflow.tool",
                            ApprovalRequest.run_id == workflow_run.id,
                            ApprovalRequest.node_id == node["id"],
                            ApprovalRequest.tool_name == tool_name,
                        )
                        .order_by(ApprovalRequest.created_at.desc())
                    )
                ).scalars().first()
                if existing is None:
                    existing = await request_approval(
                        db,
                        org_id=workflow.org_id,
                        run_type="workflow.tool",
                        run_id=workflow_run.id,
                        tool_name=tool_name,
                        node_id=node["id"],
                        args_snapshot=args,
                        requested_by=actor_user_id,
                        idempotency_key=(
                            f"workflow-tool:{workflow_run.id}:{node['id']}:{expected_hash}"
                        ),
                    )
                if existing.status == "pending":
                    raise WorkflowWaitingApproval(existing.id)
                if existing.status != "approved":
                    raise RuntimeError(f"tool approval {existing.id} was {existing.status}")
                if (
                    existing.payload_hash != expected_hash
                    or tool_args_hash(existing.args_snapshot or {}) != expected_hash
                ):
                    raise RuntimeError("approved workflow tool arguments no longer match")
                authorization = authorization.for_approved_call(
                    approval_id=existing.id,
                    approval_status=existing.status,
                    tool_name=tool_name,
                    args=args,
                )

            ctx = ToolContext(
                db=db,
                depth=0,
                workspace_dir=settings.workspace_dir,
                org_id=workflow.org_id,
                user_id=actor_user_id,
                root_run_id=workflow_run.id,
                authorization=authorization,
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
            # On resume after a decision, this run re-enters the approval node.
            # Consult the existing request instead of creating a duplicated one:
            #   - pending  -> keep waiting on the SAME request
            #   - approved -> pass the node and continue downstream
            #   - rejected -> the node fails (honours the onError policy)
            existing = (
                await db.execute(
                    select(ApprovalRequest)
                    .where(
                        ApprovalRequest.org_id == workflow.org_id,
                        ApprovalRequest.run_type == "workflow",
                        ApprovalRequest.run_id == workflow_run.id,
                        ApprovalRequest.node_id == node["id"],
                    )
                    .order_by(ApprovalRequest.created_at.desc())
                )
            ).scalars().first()
            if existing is not None:
                if existing.status == "approved":
                    return NodeOutput(
                        text="approved",
                        data={"approved": True, "approval_id": existing.id, "reason": existing.reason},
                    )
                if existing.status == "rejected":
                    raise RuntimeError(
                        f"approval rejected: {existing.reason or 'no reason given'}"
                    )
                raise WorkflowWaitingApproval(existing.id)
            timeout_minutes = cfg.get("timeout_minutes")
            expires_at = (
                utc_now() + timedelta(minutes=int(timeout_minutes)) if timeout_minutes else None
            )
            raw_approvers = cfg.get("approver_user_ids") or []
            approver_user_ids = [str(a) for a in raw_approvers] if isinstance(raw_approvers, list) else None
            approval = await request_approval(
                db,
                org_id=workflow.org_id,
                run_type="workflow",
                run_id=workflow_run.id,
                node_id=node["id"],
                tool_name=cfg.get("tool_name"),
                args_snapshot=cfg,
                requested_by=actor_user_id,
                title=cfg.get("title") or node.get("label"),
                instructions=str(cfg.get("instructions") or ""),
                approver_user_ids=approver_user_ids,
                expires_at=expires_at,
            )
            raise WorkflowWaitingApproval(approval.id)
        if kind == "sub_workflow":
            child_workflow_id = cfg.get("workflow_id")
            if not child_workflow_id:
                raise RuntimeError("sub_workflow node missing workflow_id")
            if subworkflow_depth >= MAX_SUBWORKFLOW_DEPTH:
                raise RuntimeError(
                    f"sub_workflow nesting exceeds the maximum depth of {MAX_SUBWORKFLOW_DEPTH} "
                    "(a cycle between workflows is likely)"
                )
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
                user_role=actor_user_role,
                timezone_name=timezone_name,
                subworkflow_depth=subworkflow_depth + 1,
                # Keep the child run's Langfuse trace nested inside the
                # parent's trace instead of starting an unrelated one.
                parent_trace_id=workflow_run.id,
            )
            return NodeOutput(text=str(child_output), data={"output": child_output})
        if kind == "agent":
            return await _run_agent_node(
                node, cfg, node_run, upstream_text, db, actor_user_id, actor_user_role
            )
        raise RuntimeError(f"unknown node kind {kind}")

    async def run_node(node: dict[str, Any], db: AsyncSession) -> NodeOutput:
        cfg = node.get("parameters") or node.get("config") or {}
        retry_cfg = cfg.get("retry") or node.get("retry") or {}
        if not isinstance(retry_cfg, dict):
            retry_cfg = {}
        max_attempts = max(1, int(retry_cfg.get("max_attempts", 1) or 1))
        backoff_s = max(0.0, float(retry_cfg.get("backoff_s", 0.0) or 0.0))
        timeout_s = node.get("timeout_s") or cfg.get("timeout_s") or settings.workflow_node_default_timeout_s

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
        # A resumed run re-enters nodes that did not succeed (an approval gate
        # that was waiting, or a node mid-flight when the worker died). Those
        # already have node_run rows, so continue the attempt counter past them
        # instead of colliding with the (run_id, node_id, attempt) unique key.
        prior_attempts = await db.scalar(
            select(func.max(WorkflowNodeRun.attempt)).where(
                WorkflowNodeRun.workflow_run_id == workflow_run.id,
                WorkflowNodeRun.node_id == node["id"],
            )
        )
        attempt_base = int(prior_attempts or 0)
        for attempt in range(attempt_base + 1, attempt_base + max_attempts + 1):
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
        if selected_trigger_id and nid == selected_trigger_id:
            return True
        if selected_trigger_id and nid not in active_node_ids:
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
        # Agent nodes use this as their root_run_id (Langfuse trace id). Use
        # the same trace id as workflow_observability/triager so a
        # sub_workflow's agent nodes land in the parent's trace instead of
        # starting an unrelated one.
        n["_run_id"] = parent_trace_id or workflow_run.id
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
    first_error: str | None = None
    while True:
        # Cooperative cancellation: the run row is the shared signal between
        # the cancel endpoint and whichever executor holds the lease. Re-read
        # the persisted status (not the stale identity-map object) each round
        # so a cancel issued while a node was running stops the next round.
        persisted_status = await db.scalar(
            select(WorkflowRun.status).where(WorkflowRun.id == workflow_run.id)
        )
        if persisted_status == "cancelled":
            workflow_run.status = "cancelled"
            workflow_run.finished_at = utc_now()
            await db.commit()
            yield {
                "event": "workflow_cancelled",
                "data": {"workflow_run_id": workflow_run.id},
            }
            await resume.release_lease(db, workflow_run.id)
            return
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
                    first_error = first_error or str(res)
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
    workflow_run.error = first_error
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
    user_role: str | None = None,
    timezone_name: str | None = None,
    trigger_node_id: str | None = None,
    trigger_type: str | None = None,
    subworkflow_depth: int = 0,
    parent_trace_id: str | None = None,
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
            user_role=user_role,
            timezone_name=timezone_name,
            trigger_node_id=trigger_node_id,
            trigger_type=trigger_type,
            subworkflow_depth=subworkflow_depth,
            parent_trace_id=parent_trace_id,
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
    user_role: str | None = None,
    timezone_name: str | None = None,
    trigger_node_id: str | None = None,
    trigger_type: str | None = None,
    subworkflow_depth: int = 0,
    parent_trace_id: str | None = None,
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
            user_role=user_role,
            timezone_name=timezone_name,
            trigger_node_id=trigger_node_id,
            trigger_type=trigger_type,
            subworkflow_depth=subworkflow_depth,
            parent_trace_id=parent_trace_id,
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
        trigger_node_id=trigger_node_id,
        trigger_type=trigger_type,
        subworkflow_depth=subworkflow_depth,
        parent_trace_id=parent_trace_id,
    ):
        log.append(ev)
        if ev["event"] == "workflow_start":
            workflow_run_id_seen = ev["data"]["workflow_run_id"]
        if ev["event"] == "done":
            final = ev["data"].get("output", final)
    return final, log, workflow_run_id_seen
