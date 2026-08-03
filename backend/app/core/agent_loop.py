from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.compactor import compact_session
from app.core.guardrails.approval import request_approval
from app.core.guardrails.budget import BudgetTracker, RunBudget
from app.core.guardrails.injection import wrap_untrusted_if_flagged
from app.core.guardrails.secrets import scan_and_redact
from app.core.llm import LLMClient, resolve_api_key
from app.core.observability import genai
from app.core.observability.audit import log_action
from app.core.observability.metrics import (
    agent_run_cost_usd_total,
    guardrail_events_total,
    tool_call_duration_seconds,
    tool_calls_total,
)
from app.core.tools.registry import BUILTIN_TOOLS, execute_tool_call
from app.core.tools.types import ToolContext, tool_to_openai_schema
from app.core.workflow.replay import ReplayCursor, ReplayDiverged, record_tool_call
from app.db.base import gen_id, utc_now
from app.mcp.client import build_mcp_tool_spec, get_mcp_manager
from app.models.agent import Agent
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


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def _build_specs(agent: Agent, db: AsyncSession) -> list[Any]:
    specs: list[Any] = []
    for name in agent.tools or []:
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
    res = await db.execute(select(Message).where(Message.session_id == session_id))
    count = len(res.scalars().all())
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
    task.status = status
    task.result = result
    task.cost_usd = cost_usd
    task.token_usage = token_usage or {}
    task.finished_at = utc_now()
    await db.commit()


async def _agent_stream(
    agent: Agent,
    message: str,
    db: AsyncSession,
    depth: int,
    session_id: str | None,
    current_task_id: str | None = None,
    root_run_id: str | None = None,
    replay_cursor: ReplayCursor | None = None,
) -> AsyncIterator[dict[str, Any]]:
    root_task: Task | None = None
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

    res = await db.execute(select(Model).where(Model.id == agent.model_id))
    model = res.scalar_one_or_none()
    if model is None:
        msg = (
            "no model assigned to this agent — assign one before chatting"
            if agent.model_id is None
            else f"model {agent.model_id} not found"
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
        user_id=agent.created_by_user_id,
        current_task_id=current_task_id,
        root_run_id=root_run_id or session_id or current_task_id,
    )

    specs = await _build_specs(agent, db)
    tool_schemas = [tool_to_openai_schema(s) for s in specs] if specs else None
    tool_by_name = {s.name: s for s in specs}

    # Auto-inject behavioral directives ONLY for tools the agent actually has
    # registered, so unused agents aren't burdened with irrelevant instructions.
    directives: list[str] = []
    if {"save_memory", "call_memory"} & tool_by_name.keys():
        directives.append(MEMORY_DIRECTIVE)
    if "rag_search" in tool_by_name:
        directives.append(RAG_DIRECTIVE)
    if agent.kind == "orchestrator":
        directives.append(ORCHESTRATOR_SYSTEM_SUFFIX)

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
            # Compact older messages via LLM summarization to save context tokens
            compacted = await compact_session(session_id, db, model, provider, keep_last=8)
            messages.append({"role": "system", "content": f"[Conversation context]\n{compacted}"})
        else:
            for m in hist:
                messages.append(_to_openai_message(m))
    messages.append({"role": "user", "content": message})

    if session_id:
        await _persist(
            db,
            session_id,
            "user",
            message,
            {},
            org_id=agent.org_id,
            created_by_user_id=agent.created_by_user_id,
        )

    start = time.monotonic()
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

    for _ in range(agent.max_iterations):
        content_parts: list[str] = []
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
                stream_iter = llm.stream(messages, tools=tool_schemas, temperature=agent.temperature)
                async for ev in stream_iter:
                    if ev["type"] == "content":
                        content_parts.append(ev["text"])
                        yield {"event": "token", "data": {"content": ev["text"]}}
                    elif ev["type"] == "tool_calls":
                        for tc in ev["tool_calls"]:
                            idx = tc.index
                            entry = tc_map.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                            if tc.id:
                                entry["id"] = tc.id
                            if tc.function and tc.function.name:
                                entry["name"] = tc.function.name
                            if tc.function and tc.function.arguments:
                                entry["arguments"] += tc.function.arguments
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
                for entry in tc_map.values():
                    name = entry["name"]
                    try:
                        args = json.loads(entry["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    spec = tool_by_name.get(name)
                    yield {"event": "tool_call", "data": {"name": name, "arguments": args}}
                    if spec is None:
                        result = f"error: tool '{name}' not available"
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
                                actor_user_id=agent.created_by_user_id,
                                action="guardrail.budget_exceeded",
                                resource_type="tool",
                                resource_id=name,
                                metadata={"reason": budget_reason, "run_id": session_id},
                                commit=False,
                            )
                            yield {
                                "event": "budget_exceeded",
                                "data": {"reason": budget_reason, "tool": name},
                            }
                            yield {
                                "event": "tool_result",
                                "data": {"name": name, "result": result},
                            }
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
                                actor_user_id=agent.created_by_user_id,
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
                                run_id=session_id,
                                tool_name=name,
                                args_snapshot=args,
                                requested_by=agent.created_by_user_id,
                            )
                            guardrail_events_total.labels(
                                agent.org_id, "approval_required", "paused"
                            ).inc()
                            await log_action(
                                db,
                                org_id=agent.org_id,
                                actor_user_id=agent.created_by_user_id,
                                action="guardrail.approval_required",
                                resource_type="approval_request",
                                resource_id=approval.id,
                                metadata={"tool_name": name, "run_id": session_id},
                                commit=False,
                            )
                            yield {
                                "event": "approval_required",
                                "data": {
                                    "approval_id": approval.id,
                                    "tool_name": name,
                                    "run_id": session_id,
                                },
                            }
                            await _finish_task(
                                db,
                                root_task,
                                status="waiting_approval",
                                result=f"approval required for tool '{name}'",
                            )
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
                                yield {
                                    "event": "replay_diverged",
                                    "data": {
                                        "sequence": exc.sequence,
                                        "expected": exc.expected,
                                        "requested": exc.requested,
                                    },
                                }
                                await _finish_task(
                                    db, root_task, status="diverged", result=str(exc)
                                )
                                return
                        else:
                            tool_started = time.monotonic()
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
                                    result = await execute_tool_call(spec, args, ctx)
                                tool_calls_total.labels(name, "ok").inc()
                                tool_status = "ok"
                            except Exception as e:  # noqa: BLE001
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
                                actor_user_id=agent.created_by_user_id,
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
                                    actor_user_id=agent.created_by_user_id,
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
                                actor_user_id=agent.created_by_user_id,
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
                            actor_user_id=agent.created_by_user_id,
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
                    yield {
                        "event": "tool_result",
                        "data": {"name": name, "result": result},
                    }
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
                    yield {
                        "event": "retry",
                        "data": {"attempt": consecutive_failures, "max": max_retries},
                    }
                    yield {
                        "event": "self_correct",
                        "data": {"status": "retrying", "failures": consecutive_failures},
                    }
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
                    yield {
                        "event": "self_correct",
                        "data": {"status": "circuit_breaker", "failures": consecutive_failures},
                    }
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
            yield {
                "event": "message_done",
                "data": {
                    "content": final,
                    "usage": usage,
                    "cost_usd": cost,
                    "latency_ms": elapsed,
                    "tools": tool_calls_log,
                    "session_id": session_id,
                    "model": model_label,
                },
            }
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
                    },
                    org_id=agent.org_id,
                    created_by_user_id=agent.created_by_user_id,
                )
            db.add(
                UsageEvent(
                    org_id=agent.org_id,
                    created_by_user_id=agent.created_by_user_id,
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
    yield {
        "event": "error",
        "data": {"message": f"max iterations ({agent.max_iterations}) exceeded"},
    }


async def stream_agent(
    agent: Agent,
    message: str,
    db: AsyncSession,
    session_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    async for ev in _agent_stream(agent, message, db, 0, session_id):
        yield ev


async def run_agent_loop(
    agent: Agent,
    message: str,
    db: AsyncSession,
    depth: int = 0,
    session_id: str | None = None,
    current_task_id: str | None = None,
    root_run_id: str | None = None,
    replay_cursor: ReplayCursor | None = None,
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
