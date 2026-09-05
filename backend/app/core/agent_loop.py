from __future__ import annotations

import asyncio
import copy
import json
import re
import time
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from datetime import timedelta
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import session_log as slog
from app.core.chat_events import ChatEventRecorder
from app.core.execution_policy import (
    ExecutionPolicy,
    build_execution_policy_context,
    policy_allows_tier,
)
from app.core.guardrails.approval import request_approval
from app.core.guardrails.budget import BudgetTracker, RunBudget
from app.core.guardrails.injection import wrap_untrusted_if_flagged
from app.core.guardrails.secrets import scan_and_redact
from app.core.llm import LLMClient
from app.core.memory.tiers import compact_tiered_memory
from app.core.observability import genai
from app.core.observability.audit import log_action
from app.core.observability.llm_trace import ObservabilityContext, build_trace_context
from app.core.observability.metrics import (
    agent_run_cost_usd_total,
    chat_finalization_total,
    guardrail_events_total,
    tool_call_duration_seconds,
    tool_calls_total,
)
from app.core.providers.factory import build_driver
from app.core.providers.templates import get_template
from app.core.runtime_context import build_runtime_context, normalize_timezone
from app.core.session_surface import derive_messages
from app.core.tools.authorization import (
    build_tool_authorization,
    tool_args_hash,
)
from app.core.tools.authorization import (
    requires_approval as tool_requires_approval,
)
from app.core.tools.registry import BUILTIN_TOOLS, execute_tool_call
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec, tool_to_openai_schema
from app.core.workflow.replay import ReplayCursor, ReplayDiverged, record_tool_call
from app.db.base import gen_id, utc_now
from app.db.session import SessionLocal
from app.mcp.client import build_mcp_tool_spec, get_mcp_manager
from app.models.agent import Agent
from app.models.approval_request import ApprovalRequest
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider
from app.models.task import Task
from app.models.usage import UsageEvent
from app.models.workspace import WorkspaceArtifact
from app.schemas.chat import AgentLoopResult
from app.services.quota_service import invalidate_monthly_cost_cache

settings = get_settings()
logger = structlog.get_logger(__name__)
UNTRUSTED_TOOL_SOURCES = {"web_fetch", "rag_search", "read_attachment"}

# User messages are persisted on a separate short-lived DB session while the
# provider request is starting. The task-id registry is intentionally local to
# the process: the worker that owns the agent loop also owns the deferred write.
# Every terminal path awaits and removes the entry before changing task state,
# so a failure/cancel can never race the trailing-user cleanup.
_DEFERRED_USER_WRITES: dict[
    str, asyncio.Task[None] | Coroutine[Any, Any, None]
] = {}


async def _persist_user_message_background(
    *,
    session_id: str,
    role: str,
    content: str,
    meta: dict[str, Any],
    org_id: str,
    created_by_user_id: str | None,
    db: AsyncSession | None = None,
) -> None:
    if db is not None:
        await _persist(
            db,
            session_id,
            role,
            content,
            meta,
            org_id=org_id,
            created_by_user_id=created_by_user_id,
        )
        return
    async with SessionLocal() as write_db:
        await _persist(
            write_db,
            session_id,
            role,
            content,
            meta,
            org_id=org_id,
            created_by_user_id=created_by_user_id,
        )


def defer_user_message(
    task_id: str,
    *,
    session_id: str,
    content: str,
    org_id: str,
    created_by_user_id: str | None,
    db: AsyncSession | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    previous = _DEFERRED_USER_WRITES.pop(task_id, None)
    if previous is not None:
        if isinstance(previous, asyncio.Task):
            if not previous.done():
                previous.cancel()
        else:
            previous.close()

    # The test suite uses an isolated SQLite in-memory engine whose schema is
    # only visible through the fixture session. Production keeps the separate
    # writer session so the initial provider request is not serialized behind
    # the request session's transaction.
    writer_db = None
    if db is not None:
        bind = db.get_bind()
        url = getattr(bind, "url", None)
        if (
            url is not None
            and url.drivername.startswith("sqlite")
            and url.database == ":memory:"
        ):
            writer_db = db

    write = _persist_user_message_background(
        session_id=session_id,
        role="user",
        content=content,
        meta=meta or {},
        org_id=org_id,
        created_by_user_id=created_by_user_id,
        db=writer_db,
    )
    # Do not start a coroutine on the fixture's AsyncSession until the
    # terminal barrier; AsyncSession does not permit concurrent operations.
    if writer_db is not None:
        _DEFERRED_USER_WRITES[task_id] = write
    else:
        _DEFERRED_USER_WRITES[task_id] = asyncio.create_task(write)



async def await_deferred_user_write(task_id: str | None) -> None:
    if not task_id:
        return
    pending = _DEFERRED_USER_WRITES.pop(task_id, None)
    if pending is not None:
        await pending


# Auto-injected into every agent's system prompt so the model is explicitly
# told how to use the structured memory tools. The tool schemas are provided
# by the builder; this instructs the model on the REQUIRED schema so it never
# invents free-form keys (the root cause of duplicate memory rows).
MEMORY_DIRECTIVE = (
    "Memory behavior (structured, mandatory schema):\n"
    "- Store user facts with `save_memory` using a fixed schema: "
    "memory_type in {profile, preference, project, goal, skill, relationship, "
    "history, fact} and a canonical attribute. The user's name MUST be saved as "
    "memory_type='profile', attribute='name'. Never invent custom keys.\n"
    "- Aliases are normalized automatically (full_name, formal_name, "
    "display_name, username all become profile.name), so just pass the closest "
    "attribute and the backend folds it correctly. Writes UPSERT — repeating a "
    "fact updates it, it never creates duplicates.\n"
    "- Before answering any question about the user (name, preferences, goals, "
    "context), call `call_memory` to recall what you know. To get the user's "
    "name, call `call_memory(memory_type='profile')`.\n"
)

# Injected only when the agent is registered with RAG tools. Tells the model to
# consult the knowledge base before answering factual questions, instead of
# relying solely on parametric memory.
RAG_DIRECTIVE = (
    "Retrieval behavior (RAG):\n"
    "- When the user asks a factual or document-based question that could be "
    "answered by ingested sources (technical specs, project docs, past notes, "
    "code references), call `rag_search` with a concise query BEFORE answering "
    "from prior knowledge.\n"
    "- If the knowledge base is empty or the results are off-topic, say so "
    "plainly and offer to ingest the source via rag_ingest_url / rag_ingest_text "
    "/ rag_ingest_file (or list what's available with rag_list_collections).\n"
    "- Do not claim knowledge you did not retrieve or were not told.\n"
)

ORCHESTRATOR_SYSTEM_SUFFIX = (
    "Orchestrator behavior:\n"
    "- Break the user's goal into clear sub-tasks when delegation helps.\n"
    "- Use named delegate tools (delegate_to_*) to delegate work to the single most appropriate worker agent.\n"
    "- For follow-up requests on files created in earlier turns (e.g., 'chạy luôn file đó cho tôi', 'preview it', 'run it'):\n"
    "  * DO NOT ask the worker to regenerate, recreate, edit, or check if the file exists.\n"
    "  * Instruct the worker ONLY to execute or preview the existing file directly: e.g. 'Chạy file add.py bằng run_code và trả về kết quả' or 'Xem trước file house.html bằng preview_web_artifact'.\n"
    "  * NEVER say 'Tạo file nếu chưa có' or 'tạo file' for files already discussed or created in previous turns.\n"
    "- Do NOT chain sub-agents redundantly (e.g. do not call another agent to search for a file that Software & Data Engineer just created).\n"
    "- When a sub-agent completes its work, directly synthesize its output and present the final answer and usage guidance to the user.\n"
    "- Synthesize all sub-agent results into one clear, concise final answer."
)


async def _build_orchestrator_roster(db: AsyncSession, org_id: str, exclude_agent_id: str) -> str:
    """List sibling agents in the org so an orchestrator knows what it can
    call_agent() into - target_agent_id is a raw id, not discoverable
    otherwise."""
    result = await db.execute(
        select(Agent.id, Agent.name, Agent.description).where(
            Agent.org_id == org_id, Agent.id != exclude_agent_id
        )
    )
    rows = result.all()
    if not rows:
        return ""
    lines = [f"- {row.id}: {row.name} - {row.description or 'no description'}" for row in rows]
    return "Agents available to delegate to via call_agent (id: name - description):\n" + "\n".join(lines)


def _infer_capabilities(agent: Agent) -> set[str]:
    """Infer routable capability tags from the agent's tools and name."""
    tags = {name.split("_", 1)[0].lower() for name in (agent.tools or []) if "_" in name}
    tags.add(agent.name.lower())
    return tags


def _delegate_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "agent"


_DELEGATE_ROSTER_CACHE_TTL_SECONDS = 30.0
_DELEGATE_ROSTER_CACHE: dict[
    tuple[str, str],
    tuple[float, str, tuple[ToolSpec, ...], dict[str, tuple[Agent, ...]]],
] = {}


async def _build_orchestrator_delegate_tools(
    db: AsyncSession, org_id: str, exclude_agent_id: str
) -> tuple[str, list[ToolSpec], dict[str, list[Agent]], dict[str, ToolSpec]]:
    """Build dynamic, named delegate tools and the capability index."""
    cache_key = (org_id, exclude_agent_id)
    cached = _DELEGATE_ROSTER_CACHE.get(cache_key)
    if cached is not None and cached[0] > time.monotonic():
        _, roster, cached_specs, cached_capabilities = cached
        specs = list(cached_specs)
        capabilities = {key: list(value) for key, value in cached_capabilities.items()}
        return roster, specs, capabilities, {spec.name: spec for spec in specs}
    result = await db.execute(
        select(Agent).where(
            Agent.org_id == org_id,
            Agent.id != exclude_agent_id,
            Agent.kind == "worker",
        )
    )
    agents = list(result.scalars().all())
    if agents:
        from app.models.org_agent_settings import OrgAgentSettings

        disabled_res = await db.execute(
            select(OrgAgentSettings.template_key).where(
                OrgAgentSettings.org_id == org_id,
                OrgAgentSettings.is_enabled.is_(False),
            )
        )
        disabled_keys = set(disabled_res.scalars().all())
        if disabled_keys:
            agents = [
                agent
                for agent in agents
                if getattr(agent, "template_key", None) not in disabled_keys
            ]
    if not agents:
        return "", [], {}, {}

    used_slugs: set[str] = set()
    delegate_specs: list[ToolSpec] = []
    capability_index: dict[str, list[Agent]] = {}
    delegate_by_agent_id: dict[str, ToolSpec] = {}
    lines: list[str] = []
    for target in agents:
        slug = _delegate_slug(target.name)
        if slug in used_slugs:
            slug = f"{slug}_{target.id.replace('-', '')[-6:]}"
        used_slugs.add(slug)
        tool_name = f"delegate_to_{slug}"
        description = target.description or (
            f"Handles: {', '.join(target.tools or [])}" if target.tools else "Delegate work to this agent."
        )

        async def run_delegate(args: dict[str, Any], ctx: ToolContext, target_id: str = target.id) -> str:
            from app.core.tools.builtins import _call_agent

            return await _call_agent(
                {"target_agent_id": target_id, "instruction": args.get("instruction", "")}, ctx
            )

        spec = ToolSpec(
            name=tool_name,
            description=description,
            input_schema={
                "type": "object",
                "properties": {"instruction": {"type": "string"}},
                "required": ["instruction"],
            },
            run=run_delegate,
            risk_tier=RiskTier.safe,
            timeout_s=300.0,
        )
        delegate_specs.append(spec)
        delegate_by_agent_id[target.id] = spec
        lines.append(f"- {target.id}: {target.name} - {description}")
        for capability in _infer_capabilities(target):
            capability_index.setdefault(capability, []).append(target)
    roster = "Agents available to delegate to via named tools:\n" + "\n".join(lines)
    _DELEGATE_ROSTER_CACHE[cache_key] = (
        time.monotonic() + _DELEGATE_ROSTER_CACHE_TTL_SECONDS,
        roster,
        tuple(delegate_specs),
        {key: tuple(value) for key, value in capability_index.items()},
    )
    return roster, delegate_specs, capability_index, delegate_by_agent_id


_ROUTING_SYNONYMS: dict[str, tuple[str, ...]] = {
    "email": ("email", "gmail", "mail", "thư"),
    "calendar": ("calendar", "lịch", "schedule", "meeting", "cuộc họp"),
    "drive": ("drive", "google drive", "gdrive"),
    "write": ("write_file", "viết code", "tao file", "tạo file", "lưu file", "save file", "code html", "code python", "lập trình"),
    "run": ("run_code", "chạy code", "execute", "thực thi", "sandbox"),
}

_GOOGLE_TOOL_PREFIXES = ("email_", "drive_", "calendar_")
_GOOGLE_RESOURCE_TERMS = {
    "email": ("email", "gmail", "mail", "thu"),
    "drive": ("drive", "file", "files", "tai lieu", "tep"),
    "calendar": ("calendar", "event", "events", "meeting", "lich", "cuoc hop", "su kien"),
}
_GOOGLE_TOOL_ACTION_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("email_remove_label", ("remove label", "go nhan", "xoa nhan")),
    ("email_apply_label", ("apply label", "add label", "gan nhan", "them nhan")),
    ("email_list_labels", ("list labels", "show labels", "danh sach nhan")),
    ("email_mark_unread", ("mark unread", "danh dau chua doc")),
    ("email_mark_read", ("mark read", "danh dau da doc")),
    ("email_unstar", ("unstar", "remove star", "bo sao")),
    ("email_star", ("star", "gan sao", "danh dau sao")),
    ("email_archive", ("archive", "luu tru")),
    ("email_restore", ("restore", "khoi phuc")),
    ("email_trash", ("trash", "move to trash", "bo vao thung rac", "xoa mail", "xoa email")),
    ("email_reply", ("reply", "tra loi", "phan hoi")),
    ("email_forward", ("forward", "chuyen tiep")),
    ("email_send", ("send draft", "gui ban nhap")),
    ("email_create_draft", ("create draft", "draft email", "compose email", "soan email", "tao ban nhap")),
    ("email_get", ("email id", "message id", "provider message id", "ma email", "ma thu")),
    ("email_search", ("search", "find", "filter", "tim", "kiem", "hom nay", "hom qua", "today", "yesterday", "date", "ngay", "week", "tuan", "month", "thang")),
    ("email_list_new", ("inbox", "new mail", "new email", "unread", "mail moi", "email moi", "thu moi", "chua doc")),
    ("drive_delete_file", ("delete", "remove", "xoa")),
    ("drive_update_file", ("update", "edit", "rename", "cap nhat", "sua", "doi ten")),
    ("drive_create_file", ("create", "new file", "tao", "tep moi", "tai lieu moi")),
    ("drive_get_file", ("file id", "provider file id", "ma file", "ma tep", "ma tai lieu")),
    ("drive_list_files", ("search", "find", "list", "show", "tim", "kiem", "liet ke", "danh sach")),
    ("calendar_delete_event", ("delete", "cancel", "xoa", "huy")),
    ("calendar_update_event", ("update", "edit", "reschedule", "cap nhat", "sua", "doi lich")),
    ("calendar_create_event", ("create", "schedule", "book", "tao", "dat lich", "len lich")),
    ("calendar_get_event", ("event id", "provider event id", "ma event", "ma su kien")),
    ("calendar_list_events", ("search", "find", "list", "show", "today", "tomorrow", "tim", "kiem", "liet ke", "danh sach", "hom nay", "ngay mai")),
)
_GOOGLE_LOOKUP_FALLBACK_TOOLS = {
    "email_get",
    "email_list_new",
    "drive_get_file",
    "drive_list_files",
    "calendar_get_event",
    "calendar_list_events",
}

_STICKY_ROUTE_TTL_MINUTES = 30
_STICKY_ROUTE_LOOKBACK = 5
_SHORT_FOLLOWUP_MAX_WORDS = 8


async def _recent_delegate_agent_id(
    db: AsyncSession,
    org_id: str,
    root_run_id: str | None,
    exclude_agent_id: str,
    session_id: str | None = None,
) -> str | None:
    """Return the sole recent delegated agent for short follow-up routing.

    A root run groups one delegation tree, while a chat session can contain
    multiple root runs across turns. Use the structured session checkpoint as
    the cross-turn fallback rather than searching free-form conversation text.
    """
    if not root_run_id and not session_id:
        return None
    cutoff = utc_now() - timedelta(minutes=_STICKY_ROUTE_TTL_MINUTES)
    scope = []
    if root_run_id:
        scope.append(Task.root_run_id == root_run_id)
    if session_id:
        scope.append(Task.progress["session_id"].as_string() == session_id)
    res = await db.execute(
        select(Task.agent_id)
        .where(
            Task.org_id == org_id,
            or_(*scope),
            Task.agent_id != exclude_agent_id,
            Task.started_at >= cutoff,
        )
        .order_by(Task.started_at.desc())
        .limit(_STICKY_ROUTE_LOOKBACK)
    )
    agent_ids = {row[0] for row in res.all() if row[0]}
    return next(iter(agent_ids)) if len(agent_ids) == 1 else None


def _route_orchestrator_turn(
    message: str,
    delegate_specs: list[ToolSpec],
    capability_index: dict[str, list[Agent]],
    delegate_by_agent_id: dict[str, ToolSpec] | None = None,
    sticky_agent_id: str | None = None,
) -> tuple[dict[str, Any] | str, str | None]:
    """Return a forced delegate tool when one capability has one candidate."""
    text = message.lower()
    matched: dict[str, list[Agent]] = {}
    for capability, agents in capability_index.items():
        terms = _ROUTING_SYNONYMS.get(capability, (capability,))
        if any(term in text for term in terms):
            matched[capability] = agents
    candidates = {agent.id: agent for agents in matched.values() for agent in agents}
    if not candidates and sticky_agent_id and len(message.split()) <= _SHORT_FOLLOWUP_MAX_WORDS:
        spec = (delegate_by_agent_id or {}).get(sticky_agent_id)
        if spec is not None:
            return {"type": "function", "function": {"name": spec.name}}, (
                f"This short follow-up continues the recent delegation to {spec.name}. "
                f"You MUST call {spec.name}; do not answer or refuse directly."
            )
        return "auto", None
    if len(candidates) != 1:
        return "auto", None
    target = next(iter(candidates.values()))
    spec = (delegate_by_agent_id or {}).get(target.id)
    if spec is None:
        return "auto", None
    return {"type": "function", "function": {"name": spec.name}}, (
        f"This request matches the {next(iter(matched))} capability. You MUST call {spec.name}; do not answer or refuse directly. "
        "Pass the user's request faithfully in the delegation instruction; do not add requirements the user did not ask for."
    )


def _normalized_route_text(message: str) -> str:
    text = unicodedata.normalize("NFKD", message.lower().replace("đ", "d"))
    ascii_text = "".join(char for char in text if not unicodedata.combining(char))
    return f" {re.sub(r'[^a-z0-9]+', ' ', ascii_text).strip()} "


def _contains_route_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(f" {term} " in text for term in terms)


def _route_google_worker_tool(
    message: str, tool_by_name: dict[str, ToolSpec]
) -> dict[str, Any] | str:
    """Force one available Google integration tool for an explicit intent."""
    available_families = {
        prefix.removesuffix("_")
        for prefix in _GOOGLE_TOOL_PREFIXES
        if any(name.startswith(prefix) for name in tool_by_name)
    }
    if not available_families:
        return "auto"
    text = _normalized_route_text(message)
    matched_families = {
        family
        for family in available_families
        if _contains_route_term(text, _GOOGLE_RESOURCE_TERMS[family])
    }
    if len(matched_families) != 1:
        return "auto"
    family = next(iter(matched_families))
    candidates = [
        name
        for name, terms in _GOOGLE_TOOL_ACTION_TERMS
        if name.startswith(f"{family}_")
        and name in tool_by_name
        and _contains_route_term(text, terms)
    ]
    if not candidates:
        return "auto"
    if "email_send" in candidates:
        candidates = [name for name in candidates if name != "email_create_draft"]
    specific = [name for name in candidates if name not in _GOOGLE_LOOKUP_FALLBACK_TOOLS]
    resolved = specific or candidates
    if len(resolved) != 1:
        return "auto"
    selected = resolved[0]
    return {"type": "function", "function": {"name": selected}}


def _connected_data_directive() -> str:
    now_dt = utc_now()
    now = now_dt.isoformat(timespec="seconds") + "Z"
    today = now_dt.date()
    tomorrow = today + timedelta(days=1)
    return (
        "Connected-data tool behavior:\n"
        "- Use the relevant tool before answering requests that require current Email, Drive, or Calendar data.\n"
        "- Do not claim a connected service is inaccessible before attempting its relevant read tool.\n"
        "- Convert relative dates to provider-supported arguments. Current UTC time: "
        f"{now}. For Gmail, today's UTC range is after:{today:%Y/%m/%d} "
        f"before:{tomorrow:%Y/%m/%d}. Preserve an explicit user timezone; otherwise use UTC and state that assumption.\n"
        "- After a successful list/search read, summarize that result and stop. Do not fetch every item individually "
        "unless the user explicitly asks for message/file/event details.\n"
        "- Ask for clarification when a write action or its required details are ambiguous."
    )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def _build_specs(agent: Agent, db: AsyncSession) -> list[Any]:
    specs: list[Any] = []
    tool_names = list(agent.tools or [])
    # Keep existing persisted agent releases compatible as the connected-account
    # toolset grows. The specialized agents automatically receive the complete
    # family for their connected provider without requiring a manual republish.
    if agent.name == "email-intelligence" or any(name.startswith("email_") for name in tool_names):
        tool_names.extend(name for name in BUILTIN_TOOLS if name.startswith("email_") and name not in tool_names)
    if agent.name == "drive-researcher" or any(name.startswith("drive_") for name in tool_names):
        tool_names.extend(name for name in BUILTIN_TOOLS if name.startswith("drive_") and name not in tool_names)
    if agent.name == "calendar-intelligence" or any(name.startswith("calendar_") for name in tool_names):
        tool_names.extend(name for name in BUILTIN_TOOLS if name.startswith("calendar_") and name not in tool_names)
    for name in tool_names:
        spec = BUILTIN_TOOLS.get(name)
        if spec is not None:
            specs.append(spec)
        else:
            mcp_spec = await build_mcp_tool_spec(name, db, org_id=agent.org_id)
            if mcp_spec is not None:
                specs.append(mcp_spec)
    return specs


def _to_openai_message(m: Message) -> dict[str, Any]:
    return {"role": m.role, "content": m.content}


def _is_tool_failure(name: str, result: str) -> bool:
    """A tool result counts as a failure if it is an explicit error or a
    non-zero exit (run_code / run_shell append '[exit code: N]')."""
    r = result or ""
    if r.startswith("error:"):
        return True
    if "[exit code: " in r:
        try:
            code = int(r.rsplit("[exit code: ", 1)[1].rstrip("]").strip())
            return code != 0
        except (ValueError, IndexError):
            return False
    return False


_FINALIZATION_FALLBACK_MAX_CHARS = 12_000


def _latest_successful_tool_result(tool_calls: list[dict[str, Any]]) -> str | None:
    for call in reversed(tool_calls):
        result = str(call.get("result") or "").strip()
        if result and not _is_tool_failure(str(call.get("name") or ""), result):
            return result[:_FINALIZATION_FALLBACK_MAX_CHARS]
    return None


async def _persist(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    meta: dict[str, Any],
    org_id: str,
    created_by_user_id: str | None = None,
) -> None:
    content, findings = scan_and_redact(content)
    if findings:
        meta = {**meta, "redacted_secret_findings": [f.kind for f in findings]}
    res = await db.execute(
        select(func.count()).select_from(Message).where(Message.session_id == session_id)
    )
    count = res.scalar() or 0
    db.add(
        Message(
            org_id=org_id,
            created_by_user_id=created_by_user_id,
            session_id=session_id,
            role=role,
            content=content,
            meta=meta,
            position=count,
        )
    )
    await db.commit()


async def _delete_trailing_user_message(db: AsyncSession, session_id: str | None) -> None:
    """Remove the last message in a session if the run for it never answered.

    The user's message is persisted eagerly at run start so it appears in the
    UI immediately, before the run's outcome is known. If the run then fails
    or is orphaned (worker crashed with no assistant turn ever produced), that
    saved-but-unanswered message would otherwise stick around and get resent
    as duplicate context on the user's next try. Deleting it is safe exactly
    when it is still the last row in the session: nothing has been persisted
    after it, so no later turn depends on its position.
    """
    if not session_id:
        return
    last = (
        await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.position.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is not None and last.role == "user":
        await db.delete(last)


async def fail_chat_run(db: AsyncSession, task: Task, exc: Exception) -> None:
    """Mark a top-level chat run failed and clean up its unanswered user turn.

    Shared by both execution paths (inline ``BackgroundTasks`` and the arq
    worker) so a crash is handled identically regardless of which one ran it —
    previously only the inline path deleted the eagerly-saved user message,
    so a queued-mode failure left it to be resent as duplicate context.
    """
    await await_deferred_user_write(task.id)
    task.status = "failed"
    task.result = str(exc)
    task.finished_at = utc_now()
    await _delete_trailing_user_message(db, (task.progress or {}).get("session_id"))
    await db.commit()


async def _find_direct_child_toward(
    db: AsyncSession, from_task_id: str | None, target_task_id: str
) -> Task | None:
    """Find the direct child of ``from_task_id`` that leads to ``target_task_id``.

    Delegation can nest arbitrarily deep (call_agent inside a delegated
    sub-agent), so an approval's owning task may be several ``call_agent``
    hops below the task that is resuming. Resuming must walk one hop at a
    time — jumping straight to the owning task would skip every
    intermediate sub-agent's turn, leaving their in-flight tool call
    unanswered in their own message history. Walking up ``parent_task_id``
    from the target to whichever ancestor is a direct child of
    ``from_task_id`` gives the next single hop to recurse into; that hop
    then applies this same logic for whatever remains below it.
    """
    if from_task_id is None:
        return None
    current = (
        await db.execute(select(Task).where(Task.id == target_task_id))
    ).scalar_one_or_none()
    if current is None:
        return None
    # Cap the walk to a sane bound so a corrupted/cyclic parent chain can
    # never turn into an infinite loop.
    for _ in range(64):
        if current.parent_task_id == from_task_id:
            return current
        if current.parent_task_id is None:
            return None
        current = (
            await db.execute(select(Task).where(Task.id == current.parent_task_id))
        ).scalar_one_or_none()
        if current is None:
            return None
    return None


async def _finish_task(
    db: AsyncSession,
    task: Task | None,
    *,
    status: str,
    result: str | None = None,
    cost_usd: float = 0.0,
    token_usage: dict[str, Any] | None = None,
) -> None:
    if task is None:
        return
    await await_deferred_user_write(task.id)
    if task.status == "cancelled" and status != "cancelled":
        return
    task.status = status
    task.result = result
    task.cost_usd = cost_usd
    task.token_usage = token_usage or {}
    task.finished_at = utc_now()
    if task.parent_task_id is None and status in {"succeeded", "failed", "cancelled"} and task.root_run_id:
        try:
            await db.execute(
                update(ApprovalRequest)
                .where(
                    ApprovalRequest.run_id == task.root_run_id,
                    ApprovalRequest.status == "pending",
                )
                .values(status="expired", decided_at=utc_now(), reason="run finished")
            )
        except Exception:
            pass
    await db.commit()


async def _is_cancelled(db: AsyncSession, task: Task | None) -> bool:
    if task is None:
        return False
    await db.refresh(task, attribute_names=["status"])
    return task.status == "cancelled"


def format_multimodal_user_content(
    text: str,
    images: list[dict[str, str]],
    driver_family: str = "openai_compatible",
) -> list[dict[str, Any]]:
    """Format user text and attached images into provider-specific content blocks."""
    if driver_family == "anthropic":
        blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for img in images:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img["mime_type"],
                        "data": img["data_b64"],
                    },
                }
            )
        return blocks
    elif driver_family == "gemini":
        blocks = [{"text": text}]
        for img in images:
            blocks.append(
                {
                    "inline_data": {
                        "mime_type": img["mime_type"],
                        "data": img["data_b64"],
                    }
                }
            )
        return blocks
    else:  # openai_compatible and default
        blocks = [{"type": "text", "text": text}]
        for img in images:
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img['mime_type']};base64,{img['data_b64']}"
                    },
                }
            )
        return blocks


async def _agent_stream(
    agent: Agent,
    message: str | dict[str, Any],
    db: AsyncSession,
    depth: int,
    session_id: str | None,
    current_task_id: str | None = None,
    root_run_id: str | None = None,
    replay_cursor: ReplayCursor | None = None,
    user_id: str | None = None,
    model_id: str | None = None,
    user_role: str | None = None,
    actor_agent_identity_id: str | None = None,
    delegation_chain: list | dict | None = None,
    record_stream: bool = True,
    approval_resume_id: str | None = None,
    timezone_name: str | None = None,
    execution_policy: ExecutionPolicy | None = None,
    parent_session_id: str | None = None,
    display_message: str | None = None,
    message_meta: dict[str, Any] | None = None,
    attachment_warnings: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    def _allows_tier(tier: str) -> bool:
        if execution_policy is not None:
            return policy_allows_tier(execution_policy, tier)
        return tier in (agent.allowed_risk_tiers or [])

    if isinstance(message, dict):
        raw_message_text = str(message.get("text") or "")
        message_images = list(message.get("images") or [])
    else:
        raw_message_text = str(message or "")
        message_images = []

    phase_started_at = time.monotonic()
    turn_started_at = utc_now()
    logger.info(
        "chat_latency_phase",
        phase="agent_loop_start",
        run_id=root_run_id or current_task_id,
        task_id=current_task_id,
        depth=depth,
    )
    root_task: Task | None = None
    # A detached chat creates its durable Task before starting model work. Reuse
    # that row so status/result survive an SSE disconnect and no duplicate root
    # task is created.
    if current_task_id is not None:
        task_res = await db.execute(
            select(Task).where(Task.id == current_task_id, Task.org_id == agent.org_id)
        )
        root_task = task_res.scalar_one_or_none()
        if root_task is None:
            yield {"event": "error", "data": {"message": "chat run not found"}}
            return
        if root_task.status == "cancelled":
            return
        root_task.status = "running"
        root_task.started_at = root_task.started_at or utc_now()
        root_run_id = root_task.root_run_id
        await db.commit()
    # Position of the next tool call within this run, used to line recordings
    # up with the replay that reads them back.
    tool_sequence = 0
    if current_task_id is None:
        resolved_root_run_id = root_run_id or session_id or gen_id()
        root_task = Task(
            org_id=agent.org_id,
            parent_task_id=None,
            root_run_id=resolved_root_run_id,
            agent_id=agent.id,
            agent_release_id=getattr(agent, "active_release_id", None),
            triggered_by_user_id=user_id or agent.created_by_user_id,
            goal=raw_message_text,
            status="running",
            depth=depth,
            started_at=utc_now(),
        )
        db.add(root_task)
        await db.commit()
        await db.refresh(root_task)
        current_task_id = root_task.id
        root_run_id = root_task.root_run_id

    selected_model_id = model_id or agent.model_id
    model_stmt = select(Model).where(Model.id == selected_model_id, Model.org_id == agent.org_id)
    if model_id and user_role == "user":
        model_stmt = model_stmt.where(Model.active.is_(True))
    res = await db.execute(model_stmt)
    model = res.scalar_one_or_none()
    if model is None:
        msg = (
            "no model assigned to this agent — assign one before chatting"
            if selected_model_id is None
            else f"model {selected_model_id} not found or unavailable"
        )
        await _finish_task(db, root_task, status="failed", result=msg)
        yield {"event": "error", "data": {"message": msg}}
        return
    res = await db.execute(select(Provider).where(Provider.id == model.provider_id))
    provider = res.scalar_one_or_none()
    if provider is None:
        await _finish_task(db, root_task, status="failed", result="provider not found for model")
        yield {"event": "error", "data": {"message": "provider not found for model"}}
        return
    logger.info(
        "chat_latency_phase",
        phase="provider_context_ready",
        run_id=root_run_id or current_task_id,
        task_id=current_task_id,
        elapsed_ms=round((time.monotonic() - phase_started_at) * 1000, 1),
    )
    observability = (
        ObservabilityContext(
            build_trace_context(
                trace_id=root_run_id or current_task_id or gen_id(),
                session_id=session_id,
                org_id=agent.org_id,
                user_id=user_id or agent.created_by_user_id,
                agent_id=agent.id,
                agent_release_id=getattr(agent, "active_release_id", None),
                metadata={"run_type": "agent", "depth": depth},
            )
        )
        if settings.observability_enabled
        else None
    )
    try:
        llm = build_driver(
            provider,
            model,
            observability=observability,
            generation_name="agent-generation",
        )
    except RuntimeError as e:
        await _finish_task(db, root_task, status="failed", result=str(e))
        yield {"event": "error", "data": {"message": str(e)}}
        return

    base_prompt = agent.system_prompt or ""

    ctx = ToolContext(
        db=db,
        depth=depth,
        workspace_dir=settings.workspace_dir,
        mcp_manager=get_mcp_manager(),
        agent_id=agent.id,
        session_id=session_id,
        org_id=agent.org_id,
        user_id=user_id or agent.created_by_user_id,
        current_task_id=current_task_id,
        root_run_id=root_run_id or session_id or current_task_id,
        model_id=selected_model_id,
        actor_agent_identity_id=actor_agent_identity_id,
        delegation_chain=delegation_chain,
        parent_session_id=parent_session_id or session_id,
        authorization=build_tool_authorization(
            org_id=agent.org_id,
            user_id=user_id or agent.created_by_user_id,
            user_role=user_role,
            agent_id=agent.id,
            allowed_risk_tiers=agent.allowed_risk_tiers,
            run_id=root_run_id or session_id or current_task_id,
            principal_type="human" if user_id else "system",
            principal_id=user_id or agent.created_by_user_id,
            execution_policy=execution_policy,
            replay=replay_cursor is not None,
        ),
        timezone_name=normalize_timezone(timezone_name),
    )

    specs = await _build_specs(agent, db)
    delegate_specs: list[ToolSpec] = []
    capability_index: dict[str, list[Agent]] = {}
    delegate_by_agent_id: dict[str, ToolSpec] = {}
    forced_tool_choice: dict[str, Any] | str = "auto"
    route_directive: str | None = None
    tool_by_name = {s.name: s for s in specs}

    # Auto-inject behavioral directives ONLY for tools the agent actually has
    # registered, so unused agents aren't burdened with irrelevant instructions.
    directives: list[str] = []
    if {"save_memory", "call_memory"} & tool_by_name.keys():
        directives.append(MEMORY_DIRECTIVE)
    if "rag_search" in tool_by_name:
        directives.append(RAG_DIRECTIVE)
    if any(name.startswith(_GOOGLE_TOOL_PREFIXES) for name in tool_by_name):
        directives.append(_connected_data_directive())
    if agent.kind == "orchestrator" and "call_agent" in tool_by_name:
        directives.append(ORCHESTRATOR_SYSTEM_SUFFIX)
        roster, delegate_specs, capability_index, delegate_by_agent_id = await _build_orchestrator_delegate_tools(
            db, agent.org_id, agent.id
        )
        specs.extend(delegate_specs)
        tool_by_name.update({spec.name: spec for spec in delegate_specs})
        if roster:
            directives.append(roster)
        sticky_agent_id = await _recent_delegate_agent_id(
            db, agent.org_id, root_run_id, agent.id, session_id
        )
        forced_tool_choice, route_directive = _route_orchestrator_turn(
            raw_message_text,
            delegate_specs,
            capability_index,
            delegate_by_agent_id,
            sticky_agent_id,
        )
        if route_directive:
            directives.append(route_directive)
    elif agent.kind != "orchestrator":
        forced_tool_choice = _route_google_worker_tool(raw_message_text, tool_by_name)

    tool_schemas = [tool_to_openai_schema(s) for s in specs] if specs else None
    logger.info(
        "chat_latency_phase",
        phase="prompt_tools_ready",
        run_id=root_run_id or current_task_id,
        task_id=current_task_id,
        tool_count=len(specs),
        elapsed_ms=round((time.monotonic() - phase_started_at) * 1000, 1),
    )

    system_parts = [build_runtime_context(timezone_name)]
    if execution_policy is not None:
        system_parts.append(build_execution_policy_context(execution_policy))
    if base_prompt:
        system_parts.append(base_prompt)
    system_parts.extend(directives)
    system_prompt = "\n\n".join(system_parts)

    # Build messages: system prompt first, then conversation history, then current user message.
    # History is derived from the append-only session event log so tool-call
    # fidelity is preserved across turns ("model-visible means logged").
    # The legacy Message table is only consulted when a session has no
    # session_events yet (safe backfill path for sessions created before
    # this feature shipped).
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    effective_session_id = session_id or parent_session_id
    if effective_session_id:
        events = await slog.load_events(db, effective_session_id)
        if events:
            messages.extend(derive_messages(events, repair_crash_tail=not bool(approval_resume_id)))
        else:
            res = await db.execute(
                select(Message).where(Message.session_id == effective_session_id).order_by(Message.position)
            )
            hist = res.scalars().all()
            if len(hist) > 20:
                # Legacy sessions: still apply tiered compaction so old
                # sessions don't blow the window until they earn events.
                tiered = await compact_tiered_memory(
                    effective_session_id,
                    db,
                    model,
                    provider,
                    hot_window=8,
                    agent_id=agent.id,
                    org_id=agent.org_id,
                    created_by_user_id=user_id or agent.created_by_user_id,
                    observability=observability,
                )
                messages.append({"role": "system", "content": f"[Conversation context]\n{tiered['combined']}"})
            else:
                for m in hist:
                    messages.append(_to_openai_message(m))
    if message_images:
        template = get_template(getattr(provider, "template_key", "") or "")
        driver_family = template.driver if template else "openai_compatible"
        user_content: Any = format_multimodal_user_content(
            raw_message_text, message_images, driver_family
        )
    else:
        user_content = raw_message_text

    if not approval_resume_id:
        messages.append({"role": "user", "content": user_content})
    elif not any(m.get("role") == "user" for m in messages):
        # A freshly-created delegated sub-agent (this nested resume's
        # current_task_id did not exist before this call) has no prior turn
        # of its own in the shared session history to have carried the
        # original request - `messages` would otherwise jump straight from
        # `system` to the synthetic `assistant`/`tool` pair built below,
        # which every provider tested rejects (a tool_calls turn with no
        # preceding user turn to be responding to). Restate the goal as
        # that user turn so the conversation shape is well-formed.
        messages.append({"role": "user", "content": user_content})

    logger.info(
        "chat_latency_phase",
        phase="prompt_history_ready",
        run_id=root_run_id or current_task_id,
        task_id=current_task_id,
        history_messages=max(0, len(messages) - 1),
        elapsed_ms=round((time.monotonic() - phase_started_at) * 1000, 1),
    )

    if session_id and not approval_resume_id and root_task is not None:
        defer_user_message(
            root_task.id,
            session_id=session_id,
            content=display_message if display_message is not None else raw_message_text,
            org_id=agent.org_id,
            created_by_user_id=user_id or agent.created_by_user_id,
            db=db,
            meta=message_meta,
        )
        # Mirror the FULL prompt (with any inlined attachment text) into the
        # append-only event log, never the display-only content above - this
        # is what future turns replay as this turn's user message for the
        # model, and it must keep seeing the attachment content it read.
        try:
            await slog.append_event(
                db,
                session_id=session_id,
                org_id=agent.org_id,
                type_=slog.USER_MESSAGE,
                data={"content": user_content},
            )
        except slog.SessionEventError:
            # Malformed payload: don't poison the run, just log and proceed.
            pass

    # Only the chat root task gets a durable event log: it is the one a
    # browser reconnects to. Subagent loops (call_agent) just emit in-process.
    rec: ChatEventRecorder | None = (
        ChatEventRecorder(
            agent.org_id,
            root_run_id,
            session_id=session_id,
            model_id=selected_model_id,
        )
        if (depth == 0 and root_run_id and record_stream)
        else None
    )
    if rec is not None:
        if approval_resume_id:
            await rec.sync_seq_from_db(db)
        rec.start_liveness()

    start = time.monotonic()
    if rec is not None and not approval_resume_id:
        await rec.record({"event": "message_start", "data": {}})
        for warning_msg in (attachment_warnings or []):
            await rec.record({"event": "attachment_warning", "data": {"message": warning_msg}})
        asyncio.create_task(
            rec.flush_progress(phase="thinking", content_chars=0, reasoning_chars=0)
        )
    if not approval_resume_id:
        yield {"event": "message_start", "data": {}}
        for warning_msg in (attachment_warnings or []):
            yield {"event": "attachment_warning", "data": {"message": warning_msg}}

    tool_calls_log: list[dict[str, Any]] = []
    consecutive_failures = 0
    max_retries = max(1, min(settings.sandbox_max_retries, agent.max_iterations))
    budget = BudgetTracker(
        RunBudget(
            max_tool_calls=settings.budget_max_tool_calls,
            max_cost_usd=settings.budget_max_cost_usd,
            max_wall_seconds=settings.budget_max_wall_seconds,
            max_repeated_call=settings.budget_max_repeated_call,
        )
    )
    approved_resume_name: str | None = None
    approved_resume_args: dict[str, Any] | None = None
    approved_resume_result: str | None = None

    # Approval resumes skip the model's original tool-choice step. The
    # approval row already contains the exact arguments the user reviewed;
    # execute those arguments once, add the tool result to the conversation,
    # then let the normal loop produce the final answer.
    if approval_resume_id:
        approval_res = await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == approval_resume_id,
                ApprovalRequest.org_id == agent.org_id,
            )
        )
        approval = approval_res.scalar_one_or_none()
        if approval is None or approval.run_id != root_run_id:
            msg = "approval request not found for this chat run"
            await _finish_task(db, root_task, status="failed", result=msg)
            yield {"event": "error", "data": {"message": msg}}
            return
        if approval.status == "rejected":
            rejected_ev = {
                "event": "approval_rejected",
                "data": {"approval_id": approval.id, "tool_name": approval.tool_name},
            }
            if rec is not None:
                await rec.record(rejected_ev)
                await rec.close()
            await _finish_task(db, root_task, status="failed", result="tool approval rejected")
            yield rejected_ev
            return
        if approval.status != "approved":
            await _finish_task(db, root_task, status="waiting_approval", result="approval pending")
            return
        # Explicit ownership routing: an approval raised inside a delegated
        # sub-agent (call_agent / delegate_to_*, possibly several levels
        # deep) must execute in *that* task's agent context, not this one's -
        # tool_by_name here only has this agent's tools, so looking the tool
        # up directly would either 404 ("tool not available") or, worse,
        # silently run a same-named tool belonging to the wrong agent. NULL
        # owning_task_id means "this task" (rows from before this column
        # existed, and direct non-delegated approvals), so it falls through
        # to the existing direct-execution path unchanged.
        owning_task_id = approval.owning_task_id
        if owning_task_id and owning_task_id != current_task_id:
            next_hop = await _find_direct_child_toward(db, current_task_id, owning_task_id)
            if next_hop is None:
                msg = f"approval '{approval.id}' does not belong to this run's delegation tree"
                await _finish_task(db, root_task, status="failed", result=msg)
                yield {"event": "error", "data": {"message": msg}}
                return
            child_agent_res = await db.execute(
                select(Agent).where(Agent.id == next_hop.agent_id, Agent.org_id == agent.org_id)
            )
            child_agent = child_agent_res.scalar_one_or_none()
            if child_agent is None:
                msg = f"error: delegated agent for task '{next_hop.id}' not found"
                await _finish_task(db, root_task, status="failed", result=msg)
                yield {"event": "error", "data": {"message": msg}}
                return
            # The nested run streams its own events (message_start, tokens,
            # nested tool calls, its own message_done) live to this same
            # client - identical to a fresh call_agent invocation - then this
            # frame folds its final answer back into *this* agent's message
            # history and lets the normal loop continue, exactly like
            # _call_agent's non-resume path does.
            #
            # The synthetic assistant/tool message pair below must reference
            # a tool name that actually exists in this agent's tool schema -
            # an orchestrator's delegate tools are dynamically named per
            # target agent (delegate_to_<slug>, built in
            # _build_orchestrator_delegate_tools), not the literal
            # "call_agent". Using the wrong name here previously made every
            # provider reject the resume with a generic "parameter is
            # invalid" 400, because the tool_call referenced a function the
            # API's own `tools` list never declared.
            resume_tool_name = "call_agent"
            resume_tool_spec = delegate_by_agent_id.get(child_agent.id)
            if resume_tool_spec is not None:
                resume_tool_name = resume_tool_spec.name
            async for nested_ev in _agent_stream(
                child_agent,
                next_hop.goal,
                db,
                depth + 1,
                None,
                current_task_id=next_hop.id,
                root_run_id=root_run_id,
                user_id=user_id,
                user_role=user_role,
                model_id=model_id or selected_model_id,
                actor_agent_identity_id=actor_agent_identity_id,
                delegation_chain=delegation_chain,
                record_stream=False,
                approval_resume_id=approval_resume_id,
                execution_policy=execution_policy,
            ):
                ev_type = nested_ev.get("event")
                ev_data = nested_ev.get("data", {})
                if ev_type == "message_done":
                    nested_result = ev_data.get("content", "")
                elif ev_type == "approval_required":
                    prog_ev = {
                        "event": "tool_progress",
                        "data": {
                            "index": 0,
                            "name": resume_tool_name,
                            "stage": "subagent_approval_required",
                            "agent_name": child_agent.name,
                            "agent_id": child_agent.id,
                            "approval_id": ev_data.get("approval_id"),
                            "tool_name": ev_data.get("tool_name"),
                            "line": f"\n[Subagent '{child_agent.name}' requires approval for {ev_data.get('tool_name')}]\n",
                        },
                    }
                    if rec is not None:
                        await rec.record(prog_ev)
                        await rec.record(nested_ev)
                        await rec.close()
                    yield prog_ev
                    yield nested_ev
                    return
                elif ev_type in {"error", "replay_diverged"}:
                    if rec is not None:
                        await rec.record(nested_ev)
                        await rec.close()
                    yield nested_ev
                    return
                elif ev_type == "reasoning":
                    text = ev_data.get("content", "")
                    prog_ev = {
                        "event": "tool_progress",
                        "data": {
                            "index": 0,
                            "name": resume_tool_name,
                            "stage": "subagent_reasoning",
                            "agent_name": child_agent.name,
                            "agent_id": child_agent.id,
                            "content": text,
                            "line": text,
                        },
                    }
                    if rec is not None:
                        await rec.record(prog_ev)
                    yield prog_ev
                elif ev_type == "token":
                    text = ev_data.get("content", "")
                    prog_ev = {
                        "event": "tool_progress",
                        "data": {
                            "index": 0,
                            "name": resume_tool_name,
                            "stage": "subagent_token",
                            "agent_name": child_agent.name,
                            "agent_id": child_agent.id,
                            "content": text,
                            "line": text,
                        },
                    }
                    if rec is not None:
                        await rec.record(prog_ev)
                    yield prog_ev
                elif ev_type == "tool_call":
                    tool_name = ev_data.get("name", "")
                    tool_args = ev_data.get("arguments", {})
                    prog_ev = {
                        "event": "tool_progress",
                        "data": {
                            "index": 0,
                            "name": resume_tool_name,
                            "stage": "subagent_tool_call",
                            "agent_name": child_agent.name,
                            "agent_id": child_agent.id,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "line": f"\n[Subagent '{child_agent.name}' calling tool: {tool_name}]\n",
                        },
                    }
                    if rec is not None:
                        await rec.record(prog_ev)
                    yield prog_ev
                elif ev_type == "tool_progress":
                    prog_ev = {
                        "event": "tool_progress",
                        "data": {
                            "index": 0,
                            "name": resume_tool_name,
                            "stage": "subagent_tool_progress",
                            "agent_name": child_agent.name,
                            "agent_id": child_agent.id,
                            **ev_data,
                        },
                    }
                    if rec is not None:
                        await rec.record(prog_ev)
                    yield prog_ev
                elif ev_type == "tool_result":
                    tool_name = ev_data.get("name", "")
                    prog_ev = {
                        "event": "tool_progress",
                        "data": {
                            "index": 0,
                            "name": resume_tool_name,
                            "stage": "subagent_tool_result",
                            "agent_name": child_agent.name,
                            "agent_id": child_agent.id,
                            "tool_name": tool_name,
                            "result": ev_data.get("result", ""),
                            "line": f"[Subagent '{child_agent.name}' tool {tool_name} completed]\n",
                        },
                    }
                    if rec is not None:
                        await rec.record(prog_ev)
                    yield prog_ev
            res_ev = {
                "event": "tool_result",
                "data": {
                    "index": 0,
                    "name": resume_tool_name,
                    "result": nested_result,
                },
            }
            if rec is not None:
                await rec.record(res_ev)
            yield res_ev
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"resume-{approval.id}",
                    "type": "function",
                    "function": {
                        "name": resume_tool_name,
                        "arguments": json.dumps(
                            {"target_agent_id": child_agent.id, "instruction": next_hop.goal}
                            if resume_tool_name == "call_agent"
                            else {"instruction": next_hop.goal},
                            ensure_ascii=False,
                        ),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": f"resume-{approval.id}",
                "content": nested_result,
            })
            approved_resume_result = nested_result
            tool_args = (
                {"target_agent_id": child_agent.id, "instruction": next_hop.goal}
                if resume_tool_name == "call_agent"
                else {"instruction": next_hop.goal}
            )
            tool_calls_log.append({
                "name": resume_tool_name,
                "arguments": tool_args,
                "result": nested_result,
                "approval_id": approval.id,
            })
            # The routing directive that forced this turn's tool_choice
            # already did its job (it is why this delegation happened at
            # all); forcing it again on the next model call - which is what
            # `_ == 0` in the main loop below would otherwise do, since this
            # is that loop's first iteration regardless of how many turns
            # preceded the approval - makes the provider reject the request:
            # the conversation now has this tool's result already, and
            # providers respond with a generic "parameter is invalid" 400
            # when forced to call it again right after being handed its own
            # output.
            forced_tool_choice = "auto"
            await db.commit()
        else:
            name = approval.tool_name or ""
            args = approval.args_snapshot or {}
            approved_resume_name = name
            approved_resume_args = args
            spec = tool_by_name.get(name)
            if spec is None:
                msg = f"error: tool '{name}' not available"
                await _finish_task(db, root_task, status="failed", result=msg)
                yield {"event": "error", "data": {"message": msg}}
                return
            tool_index = 0
            call_id = f"approval-{approval.id}"
            tool_observation = (
                observability.child(getattr(llm, "last_observation_id", None)).start_tool_observation(
                    tool_name=name,
                    tool_call_id=call_id,
                    arguments=args,
                    metadata={"risk_tier": spec.risk_tier.value, "approval_id": approval.id},
                )
                if observability is not None
                else None
            )
            budget_reason = budget.record_call(name, args)
            if budget_reason or not _allows_tier(spec.risk_tier.value):
                result = budget_reason or (
                    f"error: tool '{name}' requires risk tier '{spec.risk_tier.value}' "
                    "which is not enabled for this agent"
                )
                result_ev = {"event": "tool_result", "data": {"index": 0, "name": name, "result": result}}
                if rec is not None:
                    await rec.record(result_ev)
                    await rec.close()
                await _finish_task(db, root_task, status="failed", result=result)
                if tool_observation is not None:
                    tool_observation.finish_error(RuntimeError(result), result=result)
                yield result_ev
                return
            call_ev = {
                "event": "tool_call",
                "data": {"index": tool_index, "name": name, "arguments": args, "approved": True},
            }
            if rec is not None:
                await rec.record(call_ev)
                await rec.flush_progress(phase=f"tool:{name}")
            yield call_ev
            approved_ctx = copy.copy(ctx)
            approved_ctx.authorization = ctx.authorization.for_approved_call(
                approval_id=approval.id,
                approval_status=approval.status,
                tool_name=name,
                args=args,
            ) if ctx.authorization is not None else None
            try:
                result = await execute_tool_call(spec, args, approved_ctx)
                tool_status = "ok"
                if tool_observation is not None:
                    tool_observation.finish_success(result=result)
            except asyncio.CancelledError:
                if tool_observation is not None:
                    tool_observation.finish_cancelled()
                raise
            except Exception as exc:  # noqa: BLE001
                result = f"error executing tool: {exc}"
                tool_status = "error"
                if tool_observation is not None:
                    tool_observation.finish_error(exc, result=result)
            result, secret_findings = scan_and_redact(str(result))
            approved_resume_result = result
            await record_tool_call(
                db,
                org_id=agent.org_id,
                sequence=1,
                tool_name=name,
                arguments=args,
                result=result,
                status=tool_status,
                duration_ms=0,
                session_id=session_id,
            )
            result_ev = {"event": "tool_result", "data": {"index": tool_index, "name": name, "result": result}}
            if rec is not None:
                await rec.record(result_ev)
                await rec.heartbeat(phase="thinking")
            yield result_ev
            tool_calls_log.append({"name": name, "arguments": args, "result": result, "approval_id": approval.id})
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}],
            })
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            # Same reasoning as the delegated-resume branch above: this tool
            # call already satisfied whatever routing directive forced it,
            # so the next model call must not be forced into calling it
            # again.
            forced_tool_choice = "auto"
            await db.commit()

    finalization_retry_used = False
    finalization_outcome = "direct"

    # Running token totals across the whole run, so a mid-run budget trip can
    # persist what was actually spent onto the failed task - consistent with
    # budget.cost_usd, which also accumulates across iterations.
    usage_totals: dict[str, int] = {}

    async def _retry_finalization_without_tools() -> tuple[str, str, dict[str, int], bool, bool]:
        parts: list[str] = []
        reasoning: list[str] = []
        usage: dict[str, int] = {}
        estimated = True
        unexpected_tool_calls = False
        async for retry_ev in llm.stream(
            messages,
            tools=None,
            temperature=agent.temperature,
            thinking=agent.enable_thinking,
        ):
            if retry_ev["type"] == "content":
                parts.append(retry_ev["text"])
            elif retry_ev["type"] == "reasoning":
                reasoning.append(retry_ev["text"])
            elif retry_ev["type"] == "usage":
                usage = retry_ev["usage"]
                estimated = bool(retry_ev.get("estimated", True))
            elif retry_ev["type"] == "tool_calls":
                unexpected_tool_calls = True
        return "".join(parts), "".join(reasoning), usage, estimated, unexpected_tool_calls

    for _ in range(agent.max_iterations):
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tc_map: dict[int, dict[str, Any]] = {}
        # Real provider usage when available; the char-count heuristic below
        # is only a fallback for providers that do not report it.
        stream_usage: dict[str, int] = {}
        usage_estimated = True

        # invoke_agent is the parent of both the chat span and every
        # execute_tool span in this iteration, so a trace viewer shows one
        # tree per turn rather than a flat list of siblings.
        with genai.agent_span(agent, session_id=session_id, depth=depth):
            with genai.llm_span(
                agent,
                provider=provider,
                model_name=model.name,
                temperature=agent.temperature,
                session_id=session_id,
            ) as chat_span:
                stream_kwargs: dict[str, Any] = {
                    "tools": tool_schemas,
                    "temperature": agent.temperature,
                }
                stream_kwargs["tool_choice"] = forced_tool_choice if _ == 0 else "auto"
                logger.info(
                    "chat_latency_phase",
                    phase="provider_stream_start",
                    run_id=root_run_id or current_task_id,
                    task_id=current_task_id,
                    iteration=_,
                    elapsed_ms=round((time.monotonic() - phase_started_at) * 1000, 1),
                )
                stream_kwargs["thinking"] = agent.enable_thinking
                stream_iter = llm.stream(messages, **stream_kwargs)
                first_provider_event = True
                async for ev in stream_iter:
                    if first_provider_event:
                        first_provider_event = False
                        logger.info(
                            "chat_latency_phase",
                            phase="provider_first_event",
                            run_id=root_run_id or current_task_id,
                            task_id=current_task_id,
                            iteration=_,
                            event_type=ev.get("type"),
                            elapsed_ms=round((time.monotonic() - phase_started_at) * 1000, 1),
                        )
                    if await _is_cancelled(db, root_task):
                        if rec is not None:
                            await rec.close()
                        await await_deferred_user_write(root_task.id if root_task else None)
                        return
                    if ev["type"] == "content":
                        content_parts.append(ev["text"])
                        out_ev = {"event": "token", "data": {"content": ev["text"]}}
                        if rec is not None:
                            await rec.record(out_ev)
                            await rec.heartbeat(
                                phase="answering", content_chars=sum(map(len, content_parts))
                            )
                        yield out_ev
                    elif ev["type"] == "reasoning":
                        reasoning_parts.append(ev["text"])
                        out_ev = {"event": "reasoning", "data": {"content": ev["text"]}}
                        if rec is not None:
                            await rec.record(out_ev)
                            await rec.heartbeat(
                                phase="thinking",
                                content_chars=sum(map(len, content_parts)),
                                reasoning_chars=sum(map(len, reasoning_parts)),
                            )
                        yield out_ev
                    elif ev["type"] == "tool_calls":
                        for tc in ev["tool_calls"]:
                            # Every driver (OpenAI-compatible, Anthropic, Gemini)
                            # yields plain dicts with this shape — see
                            # LLMClient.stream's normalization of the OpenAI SDK
                            # object into the same dict contract.
                            idx = tc.get("index", 0)
                            entry = tc_map.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                            if tc.get("id"):
                                entry["id"] = tc["id"]
                            if tc.get("name"):
                                entry["name"] = tc["name"]
                            fragment = tc.get("arguments")
                            if fragment:
                                entry["arguments"] += fragment
                                # Stream the raw fragment so the UI can render
                                # tool-call arguments as they are composed,
                                # like ChatGPT/DeepSeek do — not after the
                                # whole completion finishes.
                                out_ev = {
                                    "event": "tool_call_delta",
                                    "data": {
                                        "index": idx,
                                        "id": entry["id"],
                                        "name": entry["name"],
                                        "arguments": fragment,
                                    },
                                }
                                if rec is not None:
                                    await rec.record(out_ev)
                                yield out_ev
                    elif ev["type"] == "usage":
                        stream_usage = ev["usage"]
                        usage_estimated = bool(ev.get("estimated", True))
                        genai.record_usage(
                            chat_span,
                            stream_usage,
                            org_id=agent.org_id,
                            model_name=model.name,
                            estimated=usage_estimated,
                        )
                        genai.record_finish_reasons(chat_span, ev.get("finish_reasons") or [])
                        # Feed this step's real cost into the run budget so
                        # max_cost_usd can trip mid-run, not just at the end.
                        if not usage_estimated and stream_usage:
                            for k in ("input_tokens", "output_tokens"):
                                usage_totals[k] = usage_totals.get(k, 0) + int(stream_usage.get(k, 0) or 0)
                            step_cost = LLMClient.estimate_cost(model, {
                                "input_tokens": int(stream_usage.get("input_tokens", 0) or 0),
                                "output_tokens": int(stream_usage.get("output_tokens", 0) or 0),
                            })
                            cost_reason = budget.add_cost(step_cost)
                            if cost_reason:
                                guardrail_events_total.labels(
                                    agent.org_id, "budget_exceeded", "blocked"
                                ).inc()
                                await log_action(
                                    db,
                                    org_id=agent.org_id,
                                    actor_user_id=user_id or agent.created_by_user_id,
                                    actor_agent_identity_id=actor_agent_identity_id,
                                    delegation_chain=delegation_chain,
                                    action="guardrail.budget_exceeded",
                                    resource_type="model",
                                    resource_id=model.name,
                                    metadata={"reason": cost_reason, "run_id": root_run_id or session_id},
                                    commit=False,
                                )
                                budget_ev = {
                                    "event": "budget_exceeded",
                                    "data": {"reason": cost_reason},
                                }
                                if rec is not None:
                                    await rec.record(budget_ev)
                                    await rec.close()
                                await _finish_task(
                                    db,
                                    root_task,
                                    status="failed",
                                    result=f"error: run budget exceeded: {cost_reason}",
                                    cost_usd=budget.cost_usd,
                                    token_usage={**usage_totals, "estimated": False},
                                )
                                yield budget_ev
                                return

            if tc_map:
                openai_tcs = []
                iter_failures = 0
                iter_results: list[dict[str, str]] = []
                batch_cached_results: dict[tuple[str, str], tuple[Any, str]] = {}
                for entry in tc_map.values():
                    openai_tcs.append(
                        {
                            "id": entry["id"],
                            "type": "function",
                            "function": {
                                "name": entry["name"],
                                "arguments": entry["arguments"],
                            },
                        }
                    )
                messages.append({"role": "assistant", "content": None, "tool_calls": openai_tcs})
                for idx, entry in enumerate(tc_map.values()):
                    name = entry["name"]
                    try:
                        args = json.loads(entry["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    spec = tool_by_name.get(name)
                    tool_index = idx
                    call_sig = (name, json.dumps(args, sort_keys=True))
                    approved_replay = (
                        approved_resume_name == name
                        and approved_resume_args == args
                        and approved_resume_result is not None
                    )
                    call_ev = {
                        "event": "tool_call",
                        "data": {"index": tool_index, "name": name, "arguments": args},
                    }
                    if session_id:
                        try:
                            await slog.append_event(
                                db,
                                session_id=session_id,
                                org_id=agent.org_id,
                                type_=slog.TOOL_CALL,
                                data={
                                    "tool_call_id": entry["id"],
                                    "name": name,
                                    "arguments": entry.get("arguments") or "{}",
                                    "status": "started",
                                },
                            )
                            await db.commit()
                        except slog.SessionEventError:
                            pass
                    if rec is not None:
                        await rec.record(call_ev)
                        await rec.flush_progress(phase=f"tool:{name}")
                    yield call_ev
                    tool_observation = (
                        observability.child(
                            getattr(llm, "last_observation_id", None)
                        ).start_tool_observation(
                            tool_name=name,
                            tool_call_id=entry["id"],
                            arguments=args,
                            metadata={
                                "risk_tier": spec.risk_tier.value if spec else None,
                            },
                        )
                        if observability is not None
                        else None
                    )
                    if approved_replay:
                        result = approved_resume_result
                        tool_status = "approved_replay"
                    elif call_sig in batch_cached_results:
                        # Parallel duplicate tool call in the same turn: reuse cached result
                        result, tool_status = batch_cached_results[call_sig]
                    elif spec is None:
                        result = f"error: tool '{name}' not available"
                        tool_status = "error"
                    else:
                        budget_reason = budget.record_call(name, args)
                        if budget_reason:
                            result = f"error: run budget exceeded: {budget_reason}"
                            guardrail_events_total.labels(
                                agent.org_id, "budget_exceeded", "blocked"
                            ).inc()
                            await log_action(
                                db,
                                org_id=agent.org_id,
                                actor_user_id=user_id or agent.created_by_user_id,
                                actor_agent_identity_id=actor_agent_identity_id,
                                delegation_chain=delegation_chain,
                                action="guardrail.budget_exceeded",
                                resource_type="tool",
                                resource_id=name,
                                metadata={"reason": budget_reason, "run_id": session_id},
                                commit=False,
                            )
                            budget_ev = {
                                "event": "budget_exceeded",
                                "data": {"reason": budget_reason, "tool": name},
                            }
                            result_ev = {
                                "event": "tool_result",
                                "data": {"name": name, "result": result},
                            }
                            if rec is not None:
                                await rec.record(budget_ev)
                                await rec.record(result_ev)
                            yield budget_ev
                            yield result_ev
                            tool_calls_log.append(
                                {"name": name, "arguments": args, "result": result}
                            )
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": entry["id"],
                                    "content": result,
                                }
                            )
                            await _finish_task(db, root_task, status="failed", result=result)
                            if tool_observation is not None:
                                tool_observation.finish_error(RuntimeError(result), result=result)
                            return
                        # Layer 1: risk-tier capability gate
                        if not _allows_tier(spec.risk_tier.value):
                            tool_status = "denied"
                            result = (
                                f"error: tool '{name}' requires risk tier "
                                f"'{spec.risk_tier.value}' which is not allowed by the execution policy. "
                                f"Policy: {execution_policy.value if execution_policy is not None else 'legacy-agent-tiers'}"
                            )
                            guardrail_events_total.labels(
                                agent.org_id, "risk_tier_denied", "blocked"
                            ).inc()
                            await log_action(
                                db,
                                org_id=agent.org_id,
                                actor_user_id=user_id or agent.created_by_user_id,
                                actor_agent_identity_id=actor_agent_identity_id,
                                delegation_chain=delegation_chain,
                                action="guardrail.risk_tier_denied",
                                resource_type="tool",
                                resource_id=name,
                                metadata={
                                    "required_tier": spec.risk_tier.value,
                                    "allowed_tiers": (
                                        [tier for tier in (
                                            ("safe", "read", "network")
                                            if execution_policy is not None and execution_policy.value == "read-only"
                                            else tuple(agent.allowed_risk_tiers or ())
                                        )]
                                    ),
                                    "execution_policy": (
                                        execution_policy.value if execution_policy is not None else None
                                    ),
                                    "run_id": session_id,
                                },
                                commit=False,
                            )
                        elif tool_requires_approval(spec, execution_policy):
                            approval = await request_approval(
                                db,
                                org_id=agent.org_id,
                                run_type="agent",
                                run_id=root_run_id,
                                tool_name=name,
                                args_snapshot=args,
                                requested_by=user_id or agent.created_by_user_id,
                                owning_task_id=current_task_id,
                                idempotency_key=f"{root_run_id}:{current_task_id or 'root'}:{name}:{tool_args_hash(args)}",
                            )
                            await db.commit()
                            guardrail_events_total.labels(
                                agent.org_id, "approval_required", "paused"
                            ).inc()
                            await log_action(
                                db,
                                org_id=agent.org_id,
                                actor_user_id=user_id or agent.created_by_user_id,
                                actor_agent_identity_id=actor_agent_identity_id,
                                delegation_chain=delegation_chain,
                                action="guardrail.approval_required",
                                resource_type="approval_request",
                                resource_id=approval.id,
                                metadata={"tool_name": name, "run_id": root_run_id},
                                commit=False,
                            )
                            approval_ev = {
                                "event": "approval_required",
                                "data": {
                                    "approval_id": approval.id,
                                    "tool_name": name,
                                    "run_id": root_run_id,
                                    "args_snapshot": scan_and_redact(json.dumps(args, ensure_ascii=False))[0],
                                },
                            }
                            if rec is not None:
                                await rec.record(approval_ev)
                            await _finish_task(
                                db,
                                root_task,
                                status="waiting_approval",
                                result=f"approval required for tool '{name}'",
                            )
                            if tool_observation is not None:
                                tool_observation.finish_cancelled(
                                    metadata={"approval_id": approval.id, "tool_status": "pending_approval"}
                                )
                            yield approval_ev
                            return
                        elif replay_cursor is not None:
                            # Replay never executes a tool. If the run takes a
                            # different path than the recording, stop and say
                            # where — falling through to a live call would
                            # spend money and cause side effects the operator
                            # never asked for.
                            try:
                                result = replay_cursor.next_result(name, args)
                                tool_status = "replayed"
                            except ReplayDiverged as exc:
                                diverged_ev = {
                                    "event": "replay_diverged",
                                    "data": {
                                        "sequence": exc.sequence,
                                        "expected": exc.expected,
                                        "requested": exc.requested,
                                    },
                                }
                                if rec is not None:
                                    await rec.record(diverged_ev)
                                await _finish_task(
                                    db, root_task, status="diverged", result=str(exc)
                                )
                                if tool_observation is not None:
                                    tool_observation.finish_error(exc)
                                yield diverged_ev
                                return
                        else:
                            tool_started = time.monotonic()
                            emit_q: asyncio.Queue = asyncio.Queue()

                            async def _emit(ev: dict[str, Any]) -> None:
                                await emit_q.put(ev)  # noqa: B023

                            run_ctx = copy.copy(ctx)
                            run_ctx.emit = _emit
                            run_task = asyncio.create_task(
                                execute_tool_call(spec, args, run_ctx)
                            )
                            try:
                                with (
                                    genai.tool_span(
                                        agent,
                                        tool_name=name,
                                        risk_tier=spec.risk_tier.value,
                                        call_id=entry["id"],
                                        session_id=session_id,
                                    ),
                                    tool_call_duration_seconds.labels(name).time(),
                                ):
                                    while True:
                                        if run_task.done():
                                            break
                                        try:
                                            item = await asyncio.wait_for(
                                                emit_q.get(), timeout=0.25
                                            )
                                        except asyncio.TimeoutError:  # noqa: UP041
                                            continue
                                        progress_ev = {
                                            "event": "tool_progress",
                                            "data": {"index": tool_index, "name": name, **item},
                                        }
                                        if rec is not None:
                                            await rec.record(progress_ev)
                                        yield progress_ev
                                    while not emit_q.empty():
                                        progress_ev = {
                                            "event": "tool_progress",
                                            "data": {"index": tool_index, "name": name, **emit_q.get_nowait()},
                                        }
                                        if rec is not None:
                                            await rec.record(progress_ev)
                                        yield progress_ev
                                    result = run_task.result()
                                tool_calls_total.labels(name, "ok").inc()
                                tool_status = "ok"
                            except asyncio.CancelledError:
                                run_task.cancel()
                                if tool_observation is not None:
                                    tool_observation.finish_cancelled()
                                raise
                            except Exception as e:  # noqa: BLE001
                                if not run_task.done():
                                    run_task.cancel()
                                tool_calls_total.labels(name, "error").inc()
                                result = f"error executing tool: {e}"
                                tool_status = "error"
                            # A delegated sub-agent (call_agent / delegate_to_*) that hits an
                            # approval gate returns a plain string summary instead of raising -
                            # from this loop's point of view that looked like an ordinary tool
                            # result, so the root run would otherwise answer "waiting for your
                            # approval" in text and finish as succeeded, leaving the approval
                            # permanently unreachable from the UI (no approve/reject action is
                            # ever rendered because no approval_required event was emitted for
                            # the root run). Detect it here and pause the root run the same way
                            # a direct tool call would.
                            if tool_status == "ok" and (
                                name == "call_agent" or name.startswith("delegate_to_")
                            ):
                                pending_sub_approval = await db.execute(
                                    select(ApprovalRequest).where(
                                        ApprovalRequest.run_id == root_run_id,
                                        ApprovalRequest.org_id == agent.org_id,
                                        ApprovalRequest.status == "pending",
                                    ).order_by(ApprovalRequest.created_at.desc()).limit(1)
                                )
                                sub_approval = pending_sub_approval.scalar_one_or_none()
                                if sub_approval is not None:
                                    tool_sequence += 1
                                    await record_tool_call(
                                        db,
                                        org_id=agent.org_id,
                                        sequence=tool_sequence,
                                        tool_name=name,
                                        arguments=args,
                                        result=str(result),
                                        status="ok",
                                        duration_ms=int((time.monotonic() - tool_started) * 1000),
                                        session_id=session_id,
                                    )
                                    result_ev = {
                                        "event": "tool_result",
                                        "data": {"index": tool_index, "name": name, "result": result},
                                    }
                                    if rec is not None:
                                        await rec.record(result_ev)
                                    yield result_ev
                                    approval_ev = {
                                        "event": "approval_required",
                                        "data": {
                                            "approval_id": sub_approval.id,
                                            "tool_name": sub_approval.tool_name,
                                            "run_id": root_run_id,
                                            "args_snapshot": scan_and_redact(
                                                json.dumps(sub_approval.args_snapshot or {}, ensure_ascii=False)
                                            )[0],
                                        },
                                    }
                                    if rec is not None:
                                        await rec.record(approval_ev)
                                    await _finish_task(
                                        db,
                                        root_task,
                                        status="waiting_approval",
                                        result=f"approval required for tool '{sub_approval.tool_name}'",
                                    )
                                    if tool_observation is not None:
                                        tool_observation.finish_cancelled(
                                            metadata={
                                                "approval_id": sub_approval.id,
                                                "tool_status": "pending_approval",
                                            }
                                        )
                                    yield approval_ev
                                    return
                            # Recorded so this run can be replayed later
                            # without calling the tool again.
                            tool_sequence += 1
                            await record_tool_call(
                                db,
                                org_id=agent.org_id,
                                sequence=tool_sequence,
                                tool_name=name,
                                arguments=args,
                                result=str(result),
                                status=tool_status,
                                duration_ms=int((time.monotonic() - tool_started) * 1000),
                                session_id=session_id,
                            )
                            # Every tool call is auditable evidence, not just
                            # the dangerous tier (EU AI Act Art.12). The
                            # dangerous-tier row is kept as-is so existing
                            # alerts and dashboards keep matching.
                            await log_action(
                                db,
                                org_id=agent.org_id,
                                actor_user_id=user_id or agent.created_by_user_id,
                                actor_agent_identity_id=actor_agent_identity_id,
                                delegation_chain=delegation_chain,
                                action="tool.executed",
                                resource_type="tool",
                                resource_id=name,
                                metadata={
                                    "risk_tier": spec.risk_tier.value,
                                    "status": tool_status,
                                    "run_id": session_id,
                                },
                                commit=False,
                            )
                            if spec.risk_tier.value == "dangerous":
                                await log_action(
                                    db,
                                    org_id=agent.org_id,
                                    actor_user_id=user_id or agent.created_by_user_id,
                                    actor_agent_identity_id=actor_agent_identity_id,
                                    delegation_chain=delegation_chain,
                                    action="tool.dangerous.executed",
                                    resource_type="tool",
                                    resource_id=name,
                                    metadata={"arguments": args},
                                    commit=False,
                                )
                    if name in UNTRUSTED_TOOL_SOURCES:
                        wrapped = wrap_untrusted_if_flagged(str(result), source=name)
                        if wrapped != str(result):
                            guardrail_events_total.labels(
                                agent.org_id, "injection_flagged", "wrapped"
                            ).inc()
                            await log_action(
                                db,
                                org_id=agent.org_id,
                                actor_user_id=user_id or agent.created_by_user_id,
                                actor_agent_identity_id=actor_agent_identity_id,
                                delegation_chain=delegation_chain,
                                action="guardrail.injection_flagged",
                                resource_type="tool",
                                resource_id=name,
                                # Statistics only: the flagged payload is
                                # attacker-controlled and must not be copied
                                # into the audit trail.
                                metadata={"source": name, "run_id": session_id},
                                commit=False,
                            )
                        result = wrapped
                    if tool_observation is not None:
                        if tool_status in {"ok", "approved_replay", "replayed"}:
                            tool_observation.finish_success(result=result)
                        else:
                            tool_observation.finish_error(RuntimeError(str(result)), result=result)
                    result, secret_findings = scan_and_redact(str(result))
                    if secret_findings:
                        guardrail_events_total.labels(
                            agent.org_id, "secret_redacted", "redacted"
                        ).inc()
                        await log_action(
                            db,
                            org_id=agent.org_id,
                            actor_user_id=user_id or agent.created_by_user_id,
                            actor_agent_identity_id=actor_agent_identity_id,
                            delegation_chain=delegation_chain,
                            action="guardrail.secret_redacted",
                            resource_type="tool",
                            resource_id=name,
                            # Kinds and counts only — never the secret value.
                            metadata={
                                "count": len(secret_findings),
                                "kinds": sorted({f.kind for f in secret_findings}),
                                "run_id": session_id,
                            },
                            commit=False,
                        )
                    # Mirror the tool result into the event log. The tool call
                    # was persisted before execution so a crash cannot lose it.
                    if session_id:
                        try:
                            await slog.append_event(
                                db,
                                session_id=session_id,
                                org_id=agent.org_id,
                                type_=slog.TOOL_RESULT,
                                data={
                                    "tool_call_id": entry["id"],
                                    "content": result,
                                    "status": tool_status,
                                },
                            )
                        except slog.SessionEventError:
                            pass
                    result_ev = {
                        "event": "tool_result",
                        "data": {"index": tool_index, "name": name, "result": result},
                    }
                    if rec is not None:
                        await rec.record(result_ev)
                        await rec.heartbeat(phase="thinking")
                    yield result_ev
                    batch_cached_results[call_sig] = (result, tool_status)
                    log_entry: dict[str, Any] = {"name": name, "arguments": args, "result": result}
                    if secret_findings:
                        log_entry["redacted_secret_findings"] = [f.kind for f in secret_findings]
                    tool_calls_log.append(log_entry)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": entry["id"],
                            "content": result,
                        }
                    )
                    if _is_tool_failure(name, result):
                        iter_failures += 1
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0
                    iter_results.append({"name": name, "result": str(result)})
                if iter_failures > 0 and consecutive_failures < max_retries:
                    retry_ev = {
                        "event": "retry",
                        "data": {"attempt": consecutive_failures, "max": max_retries},
                    }
                    correct_ev = {
                        "event": "self_correct",
                        "data": {"status": "retrying", "failures": consecutive_failures},
                    }
                    if rec is not None:
                        await rec.record(retry_ev)
                        await rec.record(correct_ev)
                    yield retry_ev
                    yield correct_ev
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "The previous tool call(s) failed. Errors:\n"
                                + "\n".join(
                                    f"- {r['name']}: {r['result'][:500]}"
                                    for r in iter_results
                                    if _is_tool_failure(r["name"], r["result"])
                                )
                                + "\nAnalyze the error, fix the cause (arguments or code), "
                                "and retry. Do not repeat the same mistake."
                            ),
                        }
                    )
                elif iter_failures > 0:
                    breaker_ev = {
                        "event": "self_correct",
                        "data": {"status": "circuit_breaker", "failures": consecutive_failures},
                    }
                    if rec is not None:
                        await rec.record(breaker_ev)
                    yield breaker_ev
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Tool calls have failed repeatedly and the retry limit is "
                                "reached. Stop retrying the same approach; provide a final "
                                "answer explaining the problem, or try a genuinely different "
                                "approach if one exists."
                            ),
                        }
                    )
                # One flush per iteration: the tool and guardrail audit rows
                # above were queued with commit=False to avoid a round trip
                # per tool call. Early-return paths flush via _finish_task.
                await db.commit()
                continue

            # Final answer (no tool calls this step)
            final = "".join(content_parts)
            reasoning_text = "".join(reasoning_parts)
            finalization_attempts: list[tuple[dict[str, int], bool]] = [
                (stream_usage, usage_estimated)
            ]
            if (
                not final.strip()
                and not reasoning_text.strip()
                and not finalization_retry_used
                and budget.exceeded() is None
            ):
                finalization_retry_used = True
                logger.info(
                    "chat_finalization_retry",
                    run_id=root_run_id or current_task_id,
                    task_id=current_task_id,
                )
                try:
                    (
                        retry_final,
                        retry_reasoning,
                        retry_usage,
                        retry_estimated,
                        unexpected_tool_calls,
                    ) = await _retry_finalization_without_tools()
                    finalization_attempts.append((retry_usage, retry_estimated))
                    if not retry_estimated and retry_usage:
                        for key in ("input_tokens", "output_tokens"):
                            usage_totals[key] = usage_totals.get(key, 0) + int(
                                retry_usage.get(key, 0) or 0
                            )
                        retry_cost = LLMClient.estimate_cost(model, {
                            "input_tokens": int(retry_usage.get("input_tokens", 0) or 0),
                            "output_tokens": int(retry_usage.get("output_tokens", 0) or 0),
                        })
                        retry_budget_reason = budget.add_cost(retry_cost)
                        if retry_budget_reason:
                            guardrail_events_total.labels(
                                agent.org_id, "budget_exceeded", "blocked"
                            ).inc()
                            await log_action(
                                db,
                                org_id=agent.org_id,
                                actor_user_id=user_id or agent.created_by_user_id,
                                actor_agent_identity_id=actor_agent_identity_id,
                                delegation_chain=delegation_chain,
                                action="guardrail.budget_exceeded",
                                resource_type="model",
                                resource_id=model.name,
                                metadata={
                                    "reason": retry_budget_reason,
                                    "run_id": root_run_id or session_id,
                                },
                                commit=False,
                            )
                            budget_ev = {
                                "event": "budget_exceeded",
                                "data": {"reason": retry_budget_reason},
                            }
                            if rec is not None:
                                await rec.record(budget_ev)
                                await rec.close()
                            await _finish_task(
                                db,
                                root_task,
                                status="failed",
                                result=f"error: run budget exceeded: {retry_budget_reason}",
                                cost_usd=budget.cost_usd,
                                token_usage={**usage_totals, "estimated": False},
                            )
                            yield budget_ev
                            return
                    if unexpected_tool_calls:
                        logger.warning(
                            "chat_finalization_retry_returned_tool_calls",
                            run_id=root_run_id or current_task_id,
                        )
                    final = retry_final
                    reasoning_text = retry_reasoning
                    if final.strip():
                        finalization_outcome = "retry"
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "chat_finalization_retry_failed",
                        run_id=root_run_id or current_task_id,
                        error_type=type(exc).__name__,
                    )

            if await _is_cancelled(db, root_task):
                if rec is not None:
                    await rec.close()
                await await_deferred_user_write(root_task.id if root_task else None)
                return
            if not final.strip():
                fallback = _latest_successful_tool_result(tool_calls_log)
                if fallback:
                    final, _ = scan_and_redact(fallback)
                    final = final[:_FINALIZATION_FALLBACK_MAX_CHARS].strip()
                    if final:
                        finalization_outcome = "tool_result_fallback"
                if not final.strip():
                    finalization_outcome = "incomplete"
                    chat_finalization_total.labels(finalization_outcome).inc()
                    incomplete_message = "No answer was generated. Please try again."
                    await _finish_task(
                        db,
                        root_task,
                        status="failed",
                        result=incomplete_message,
                    )
                    error_ev = {"event": "error", "data": {"message": incomplete_message}}
                    if rec is not None:
                        await rec.record(error_ev)
                        await rec.close()
                    yield error_ev
                    return

            chat_finalization_total.labels(finalization_outcome).inc()
            elapsed = int((time.monotonic() - start) * 1000)
            # Prefer the provider's reported token counts; the char-count
            # heuristic is only a fallback, and cost derived from it is a
            # guess (flagged via usage_estimated).
            reported_attempts = [
                usage for usage, estimated in finalization_attempts if not estimated
            ]
            if reported_attempts:
                in_tok = sum(int(usage.get("input_tokens", 0)) for usage in reported_attempts)
                out_tok = sum(int(usage.get("output_tokens", 0)) for usage in reported_attempts)
                usage_estimated = len(reported_attempts) != len(finalization_attempts)
            else:
                in_tok = _estimate_tokens(json.dumps(messages, ensure_ascii=False))
                out_tok = _estimate_tokens(final)
                usage_estimated = True
            cost = LLMClient.estimate_cost(model, {"input_tokens": in_tok, "output_tokens": out_tok})
            usage = {
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "estimated": usage_estimated,
            }
            model_label = model.display_name or model.name
            reasoning_text = reasoning_text or "".join(reasoning_parts)

            # Query workspace artifacts created/updated during this turn
            artifacts_list: list[dict[str, Any]] = []
            if agent.org_id:
                try:
                    task_ids = [
                        tid for tid in [current_task_id, (root_task.id if root_task else None)]
                        if tid
                    ]
                    id_conditions = []
                    if task_ids:
                        id_conditions.append(WorkspaceArtifact.task_id.in_(task_ids))
                    if session_id:
                        id_conditions.append(WorkspaceArtifact.session_id == session_id)
                        id_conditions.append(WorkspaceArtifact.root_run_id == session_id)
                    elif root_run_id:
                        id_conditions.append(WorkspaceArtifact.root_run_id == root_run_id)

                    art_filters = [
                        WorkspaceArtifact.org_id == agent.org_id,
                        WorkspaceArtifact.updated_at >= (turn_started_at - timedelta(seconds=1)),
                    ]
                    if id_conditions:
                        art_filters.append(or_(*id_conditions))

                    art_stmt = (
                        select(WorkspaceArtifact)
                        .where(*art_filters)
                        .order_by(WorkspaceArtifact.created_at.asc())
                    )
                    art_res = await db.execute(art_stmt)
                    for art in art_res.scalars().all():
                        artifacts_list.append({
                            "id": art.id,
                            "path": art.path,
                            "filename": Path(art.path).name,
                            "content_type": art.content_type,
                            "size": art.size,
                            "download_url": f"/api/workspace/artifacts/{art.id}/download",
                            "content_url": f"/api/workspace/artifacts/{art.id}/download?inline=true",
                            "source_tool": art.source_tool,
                        })
                except Exception:
                    logger.warning("failed_to_query_turn_artifacts", exc_info=True)

            done_ev = {
                "event": "message_done",
                "data": {
                    "content": final,
                    "usage": usage,
                    "cost_usd": cost,
                    "latency_ms": elapsed,
                    "tools": tool_calls_log,
                    "session_id": session_id,
                    "model": model_label,
                    "reasoning": reasoning_text,
                    "finalization": finalization_outcome,
                    "artifacts": artifacts_list,
                },
            }
            if session_id:
                # Persist only the final assistant text. Tool calls/results
                # are separate events and are projected into their own
                # provider messages.
                try:
                    await slog.append_event(
                        db,
                        session_id=session_id,
                        org_id=agent.org_id,
                        type_=slog.ASSISTANT_MESSAGE,
                        data={
                            "content": final,
                            "usage": usage,
                            "reasoning": reasoning_text,
                            "artifacts": artifacts_list,
                        },
                    )
                except slog.SessionEventError:
                    pass
            if rec is not None:
                # Record before yielding so a reconnecting client that drains
                # the log always sees the terminal event.
                await rec.record(done_ev)
                await rec.flush_progress(phase="done")
                await rec.close()
            yield done_ev
            if session_id:
                await _persist(
                    db,
                    session_id,
                    "assistant",
                    final,
                    {
                        "usage": usage,
                        "cost_usd": cost,
                        "latency_ms": elapsed,
                        "tools": tool_calls_log,
                        "model": model_label,
                        "reasoning": reasoning_text,
                        "finalization": finalization_outcome,
                        "artifacts": artifacts_list,
                    },
                    org_id=agent.org_id,
                    created_by_user_id=user_id or agent.created_by_user_id,
                )
            db.add(
                UsageEvent(
                    org_id=agent.org_id,
                    created_by_user_id=user_id or agent.created_by_user_id,
                    source="call_agent" if depth > 0 else "chat",
                    agent_name=agent.name,
                    model_name=model.name,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                    latency_ms=elapsed,
                )
            )
            await db.commit()
            await invalidate_monthly_cost_cache(agent.org_id)
            agent_run_cost_usd_total.labels(agent.org_id).inc(cost)
            await _finish_task(
                db,
                root_task,
                status="succeeded",
                result=final,
                cost_usd=cost,
                token_usage=usage,
            )
            return

    await _finish_task(
        db,
        root_task,
        status="failed",
        result=f"max iterations ({agent.max_iterations}) exceeded",
    )
    err_ev = {
        "event": "error",
        "data": {"message": f"max iterations ({agent.max_iterations}) exceeded"},
    }
    if rec is not None:
        await rec.record(err_ev)
        await rec.close()
    yield err_ev


async def run_agent_loop(
    agent: Agent,
    message: str | dict[str, Any],
    db: AsyncSession,
    depth: int = 0,
    session_id: str | None = None,
    current_task_id: str | None = None,
    root_run_id: str | None = None,
    replay_cursor: ReplayCursor | None = None,
    user_id: str | None = None,
    model_id: str | None = None,
    user_role: str | None = None,
    actor_agent_identity_id: str | None = None,
    delegation_chain: list | dict | None = None,
    record_stream: bool = True,
    approval_resume_id: str | None = None,
    timezone_name: str | None = None,
    execution_policy: ExecutionPolicy | None = None,
    parent_session_id: str | None = None,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    display_message: str | None = None,
    message_meta: dict[str, Any] | None = None,
    attachment_warnings: list[str] | None = None,
) -> AgentLoopResult:
    content = ""
    usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
    tool_calls: list[dict[str, Any]] = []
    latency_ms = 0
    cost_usd = 0.0
    error: str | None = None
    model_name: str | None = None
    async for ev in _agent_stream(
        agent,
        message,
        db,
        depth,
        session_id,
        current_task_id=current_task_id,
        root_run_id=root_run_id,
        replay_cursor=replay_cursor,
        user_id=user_id,
        model_id=model_id,
        user_role=user_role,
        actor_agent_identity_id=actor_agent_identity_id,
        delegation_chain=delegation_chain,
        record_stream=record_stream,
        approval_resume_id=approval_resume_id,
        timezone_name=timezone_name,
        execution_policy=execution_policy,
        parent_session_id=parent_session_id,
        display_message=display_message,
        message_meta=message_meta,
        attachment_warnings=attachment_warnings,
    ):
        if on_event is not None:
            try:
                await on_event(ev)
            except Exception:  # noqa: BLE001
                pass
        if ev["event"] == "message_done":
            data = ev["data"]
            content = data["content"]
            usage = data["usage"]
            tool_calls = data.get("tools", [])
            latency_ms = data["latency_ms"]
            cost_usd = float(data.get("cost_usd", 0.0) or 0.0)
            model_name = data.get("model")
        elif ev["event"] == "error":
            error = str(ev["data"].get("message") or "agent execution failed")
    return AgentLoopResult(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        error=error,
        model=model_name,
    )
