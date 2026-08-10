from __future__ import annotations

import asyncio
import copy
import json
import re
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.chat_events import ChatEventRecorder
from app.core.guardrails.approval import request_approval
from app.core.guardrails.budget import BudgetTracker, RunBudget
from app.core.guardrails.injection import wrap_untrusted_if_flagged
from app.core.guardrails.secrets import scan_and_redact
from app.core.llm import LLMClient, resolve_api_key
from app.core.memory.tiers import compact_tiered_memory
from app.core.observability import genai
from app.core.observability.audit import log_action
from app.core.observability.metrics import (
    agent_run_cost_usd_total,
    guardrail_events_total,
    tool_call_duration_seconds,
    tool_calls_total,
)
from app.core.tools.registry import BUILTIN_TOOLS, execute_tool_call
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec, tool_to_openai_schema
from app.core.workflow.replay import ReplayCursor, ReplayDiverged, record_tool_call
from app.db.base import gen_id, utc_now
from app.mcp.client import build_mcp_tool_spec, get_mcp_manager
from app.models.agent import Agent
from app.models.approval_request import ApprovalRequest
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider
from app.models.task import Task
from app.models.usage import UsageEvent
from app.schemas.chat import AgentLoopResult
from app.services.quota_service import invalidate_monthly_cost_cache

settings = get_settings()
UNTRUSTED_TOOL_SOURCES = {"web_fetch", "rag_search", "read_attachment"}

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
    "- Use `call_agent` to delegate work to suitable worker agents. You may call it "
    "multiple times, including multiple tool calls in one turn when tasks can run independently.\n"
    "- Synthesize subagent results into one concise final answer."
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


async def _build_orchestrator_delegate_tools(
    db: AsyncSession, org_id: str, exclude_agent_id: str
) -> tuple[str, list[ToolSpec], dict[str, list[Agent]], dict[str, ToolSpec]]:
    """Build dynamic, named delegate tools and the capability index."""
    result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.id != exclude_agent_id)
    )
    agents = list(result.scalars().all())
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
                risk_tier=RiskTier.execute,
            )
        delegate_specs.append(spec)
        delegate_by_agent_id[target.id] = spec
        lines.append(f"- {target.id}: {target.name} - {description}")
        for capability in _infer_capabilities(target):
            capability_index.setdefault(capability, []).append(target)
    roster = "Agents available to delegate to via named tools:\n" + "\n".join(lines)
    return roster, delegate_specs, capability_index, delegate_by_agent_id


_ROUTING_SYNONYMS: dict[str, tuple[str, ...]] = {
    "email": ("email", "gmail", "mail", "thư", "email"),
    "calendar": ("calendar", "lịch", "schedule", "meeting", "cuộc họp"),
    "drive": ("drive", "tài liệu", "document", "documents", "file", "files"),
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
        f"This request matches the {next(iter(matched))} capability. You MUST call {spec.name}; do not answer or refuse directly."
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
    task.status = "failed"
    task.result = str(exc)
    task.finished_at = utc_now()
    await _delete_trailing_user_message(db, (task.progress or {}).get("session_id"))
    await db.commit()


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
    if task.status == "cancelled" and status != "cancelled":
        return
    task.status = status
    task.result = result
    task.cost_usd = cost_usd
    task.token_usage = token_usage or {}
    task.finished_at = utc_now()
    await db.commit()


async def _is_cancelled(db: AsyncSession, task: Task | None) -> bool:
    if task is None:
        return False
    await db.refresh(task, attribute_names=["status"])
    return task.status == "cancelled"


async def _agent_stream(
    agent: Agent,
    message: str,
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
) -> AsyncIterator[dict[str, Any]]:
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
        if await _is_cancelled(db, root_task):
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
            goal=message,
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
    try:
        llm = LLMClient(provider.base_url, resolve_api_key(provider), model.name)
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
        actor_agent_identity_id=actor_agent_identity_id,
        delegation_chain=delegation_chain,
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
            message,
            delegate_specs,
            capability_index,
            delegate_by_agent_id,
            sticky_agent_id,
        )
        if route_directive:
            directives.append(route_directive)

    tool_schemas = [tool_to_openai_schema(s) for s in specs] if specs else None

    system_parts = [base_prompt] if base_prompt else []
    system_parts.extend(directives)
    system_prompt = "\n\n".join(system_parts)

    # Build messages: system prompt first, then conversation history, then current user message.
    # NOTE: previously messages was built before system_prompt and then overwritten here —
    # that caused history + user message to be lost entirely.
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if session_id:
        res = await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.position)
        )
        hist = res.scalars().all()
        if len(hist) > 20:
            # Compact older messages via hierarchical memory tiering (Hot/Warm/Cold)
            tiered = await compact_tiered_memory(
                session_id,
                db,
                model,
                provider,
                hot_window=8,
                agent_id=agent.id,
                org_id=agent.org_id,
                created_by_user_id=user_id or agent.created_by_user_id,
            )
            messages.append({"role": "system", "content": f"[Conversation context]\n{tiered['combined']}"})
        else:
            for m in hist:
                messages.append(_to_openai_message(m))
    if not approval_resume_id:
        messages.append({"role": "user", "content": message})

    if session_id and not approval_resume_id:
        await _persist(
            db,
            session_id,
            "user",
            message,
            {},
            org_id=agent.org_id,
            created_by_user_id=user_id or agent.created_by_user_id,
        )

    # Only the chat root task gets a durable event log: it is the one a
    # browser reconnects to. Subagent loops (call_agent) just emit in-process.
    rec: ChatEventRecorder | None = (
        ChatEventRecorder(agent.org_id, root_run_id, session_id=session_id)
        if (depth == 0 and root_run_id and record_stream)
        else None
    )
    if rec is not None:
        rec.start_liveness()

    start = time.monotonic()
    if rec is not None:
        await rec.record({"event": "message_start", "data": {}})
        await rec.flush_progress(phase="thinking", content_chars=0, reasoning_chars=0)
    yield {"event": "message_start", "data": {}}

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
        budget_reason = budget.record_call(name, args)
        if budget_reason or spec.risk_tier.value not in agent.allowed_risk_tiers:
            result = budget_reason or (
                f"error: tool '{name}' requires risk tier '{spec.risk_tier.value}' "
                "which is not enabled for this agent"
            )
            result_ev = {"event": "tool_result", "data": {"index": 0, "name": name, "result": result}}
            if rec is not None:
                await rec.record(result_ev)
                await rec.close()
            await _finish_task(db, root_task, status="failed", result=result)
            yield result_ev
            return
        tool_index = 0
        call_id = f"approval-{approval.id}"
        call_ev = {
            "event": "tool_call",
            "data": {"index": tool_index, "name": name, "arguments": args, "approved": True},
        }
        if rec is not None:
            await rec.record(call_ev)
            await rec.flush_progress(phase=f"tool:{name}")
        yield call_ev
        try:
            result = await execute_tool_call(spec, args, ctx)
            tool_status = "ok"
        except Exception as exc:  # noqa: BLE001
            result = f"error executing tool: {exc}"
            tool_status = "error"
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
        await db.commit()

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
                if agent.kind == "orchestrator":
                    stream_kwargs["tool_choice"] = forced_tool_choice if _ == 0 else "auto"
                stream_iter = llm.stream(messages, **stream_kwargs)
                async for ev in stream_iter:
                    if await _is_cancelled(db, root_task):
                        if rec is not None:
                            await rec.close()
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
                            idx = tc.index
                            entry = tc_map.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                            if tc.id:
                                entry["id"] = tc.id
                            if tc.function and tc.function.name:
                                entry["name"] = tc.function.name
                            if tc.function and tc.function.arguments:
                                fragment = tc.function.arguments
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

            if tc_map:
                openai_tcs = []
                iter_failures = 0
                iter_results: list[dict[str, str]] = []
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
                    approved_replay = (
                        approved_resume_name == name
                        and approved_resume_args == args
                        and approved_resume_result is not None
                    )
                    call_ev = {
                        "event": "tool_call",
                        "data": {"index": tool_index, "name": name, "arguments": args},
                    }
                    if rec is not None:
                        await rec.record(call_ev)
                        await rec.flush_progress(phase=f"tool:{name}")
                    yield call_ev
                    if approved_replay:
                        result = approved_resume_result
                        tool_status = "approved_replay"
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
                            return
                        # Layer 1: risk-tier capability gate
                        if spec.risk_tier.value not in agent.allowed_risk_tiers:
                            result = (
                                f"error: tool '{name}' requires risk tier "
                                f"'{spec.risk_tier.value}' which is not enabled for this agent. "
                                f"Allowed tiers: {agent.allowed_risk_tiers}"
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
                                    "allowed_tiers": list(agent.allowed_risk_tiers or []),
                                    "run_id": session_id,
                                },
                                commit=False,
                            )
                        elif spec.requires_approval:
                            approval = await request_approval(
                                db,
                                org_id=agent.org_id,
                                run_type="agent",
                                run_id=root_run_id,
                                tool_name=name,
                                args_snapshot=args,
                                requested_by=user_id or agent.created_by_user_id,
                            )
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
                                raise
                            except Exception as e:  # noqa: BLE001
                                if not run_task.done():
                                    run_task.cancel()
                                tool_calls_total.labels(name, "error").inc()
                                result = f"error executing tool: {e}"
                                tool_status = "error"
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
                    result_ev = {
                        "event": "tool_result",
                        "data": {"index": tool_index, "name": name, "result": result},
                    }
                    if rec is not None:
                        await rec.record(result_ev)
                        await rec.heartbeat(phase="thinking")
                    yield result_ev
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
            if await _is_cancelled(db, root_task):
                if rec is not None:
                    await rec.close()
                return
            elapsed = int((time.monotonic() - start) * 1000)
            # Prefer the provider's reported token counts; the char-count
            # heuristic is only a fallback, and cost derived from it is a
            # guess (flagged via usage_estimated).
            if stream_usage and not usage_estimated:
                in_tok = int(stream_usage.get("input_tokens", 0))
                out_tok = int(stream_usage.get("output_tokens", 0))
            else:
                in_tok = _estimate_tokens(json.dumps(messages, ensure_ascii=False))
                out_tok = _estimate_tokens(final)
            cost = LLMClient.estimate_cost(model, {"input_tokens": in_tok, "output_tokens": out_tok})
            usage = {
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "estimated": usage_estimated,
            }
            model_label = model.display_name or model.name
            reasoning_text = "".join(reasoning_parts)
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
                },
            }
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
    message: str,
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
) -> AgentLoopResult:
    content = ""
    usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
    tool_calls: list[dict[str, Any]] = []
    latency_ms = 0
    cost_usd = 0.0
    error: str | None = None
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
    ):
        if ev["event"] == "message_done":
            data = ev["data"]
            content = data["content"]
            usage = data["usage"]
            tool_calls = data.get("tools", [])
            latency_ms = data["latency_ms"]
            cost_usd = float(data.get("cost_usd", 0.0) or 0.0)
        elif ev["event"] == "error":
            error = str(ev["data"].get("message") or "agent execution failed")
    return AgentLoopResult(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        error=error,
    )
