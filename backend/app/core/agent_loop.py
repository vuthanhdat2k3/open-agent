from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.compactor import compact_session
from app.core.llm import LLMClient, resolve_api_key
from app.core.tools.registry import BUILTIN_TOOLS
from app.core.tools.types import ToolContext, tool_to_openai_schema
from app.mcp.client import build_mcp_tool_spec, get_mcp_manager
from app.models.agent import Agent
from app.models.message import Message
from app.models.model import Model
from app.models.provider import Provider
from app.models.usage import UsageEvent
from app.schemas.chat import AgentLoopResult

settings = get_settings()

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


async def _agent_stream(
    agent: Agent,
    message: str,
    db: AsyncSession,
    depth: int,
    session_id: str | None,
) -> AsyncIterator[dict[str, Any]]:
    res = await db.execute(select(Model).where(Model.id == agent.model_id))
    model = res.scalar_one_or_none()
    if model is None:
        yield {"event": "error", "data": {"message": f"model {agent.model_id} not found"}}
        return
    res = await db.execute(select(Provider).where(Provider.id == model.provider_id))
    provider = res.scalar_one_or_none()
    if provider is None:
        yield {"event": "error", "data": {"message": "provider not found for model"}}
        return
    try:
        llm = LLMClient(provider.base_url, resolve_api_key(provider), model.name)
    except RuntimeError as e:
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

    for _ in range(agent.max_iterations):
        content_parts: list[str] = []
        tc_map: dict[int, dict[str, Any]] = {}

        async for ev in llm.stream(messages, tools=tool_schemas, temperature=agent.temperature):
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
                    try:
                        result = await spec.run(args, ctx)
                    except Exception as e:  # noqa: BLE001
                        result = f"error executing tool: {e}"
                yield {
                    "event": "tool_result",
                    "data": {"name": name, "result": str(result)},
                }
                tool_calls_log.append({"name": name, "arguments": args, "result": str(result)})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": entry["id"],
                        "content": str(result),
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
            continue

        # Final answer (no tool calls this step)
        final = "".join(content_parts)
        elapsed = int((time.monotonic() - start) * 1000)
        in_tok = _estimate_tokens(json.dumps(messages, ensure_ascii=False))
        out_tok = _estimate_tokens(final)
        cost = LLMClient.estimate_cost(model, {"input_tokens": in_tok, "output_tokens": out_tok})
        usage = {"input_tokens": in_tok, "output_tokens": out_tok}
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
        return

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
) -> AgentLoopResult:
    content = ""
    usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
    tool_calls: list[dict[str, Any]] = []
    latency_ms = 0
    async for ev in _agent_stream(agent, message, db, depth, session_id):
        if ev["event"] == "message_done":
            data = ev["data"]
            content = data["content"]
            usage = data["usage"]
            tool_calls = data.get("tools", [])
            latency_ms = data["latency_ms"]
    return AgentLoopResult(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        latency_ms=latency_ms,
    )
