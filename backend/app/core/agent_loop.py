from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Optional

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


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


async def _build_specs(agent: Agent, db: AsyncSession) -> list[Any]:
    specs: list[Any] = []
    for name in agent.tools or []:
        spec = BUILTIN_TOOLS.get(name)
        if spec is not None:
            specs.append(spec)
        else:
            mcp_spec = await build_mcp_tool_spec(name, db)
            if mcp_spec is not None:
                specs.append(mcp_spec)
    return specs


def _to_openai_message(m: Message) -> dict[str, Any]:
    return {"role": m.role, "content": m.content}


async def _persist(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    meta: dict[str, Any],
) -> None:
    res = await db.execute(
        select(Message).where(Message.session_id == session_id)
    )
    count = len(res.scalars().all())
    db.add(
        Message(
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
    session_id: Optional[str],
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

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": agent.system_prompt or ""}
    ]
    if session_id:
        res = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.position)
        )
        hist = res.scalars().all()
        if len(hist) > 20:
            # Compact older messages via LLM summarization to save context tokens
            compacted = await compact_session(
                session_id, db, model, provider, keep_last=8
            )
            messages.append({"role": "system", "content": f"[Conversation context]\n{compacted}"})
        else:
            for m in hist:
                messages.append(_to_openai_message(m))
    messages.append({"role": "user", "content": message})

    if session_id:
        await _persist(db, session_id, "user", message, {})

    ctx = ToolContext(
        db=db,
        depth=depth,
        workspace_dir=settings.workspace_dir,
        mcp_manager=get_mcp_manager(),
        agent_id=agent.id,
        session_id=session_id,
    )

    specs = await _build_specs(agent, db)
    tool_schemas = (
        [tool_to_openai_schema(s) for s in specs] if specs else None
    )
    tool_by_name = {s.name: s for s in specs}

    start = time.monotonic()
    yield {"event": "message_start", "data": {}}

    tool_calls_log: list[dict[str, Any]] = []

    for _ in range(agent.max_iterations):
        content_parts: list[str] = []
        tc_map: dict[int, dict[str, Any]] = {}

        async for ev in llm.stream(
            messages, tools=tool_schemas, temperature=agent.temperature
        ):
            if ev["type"] == "content":
                content_parts.append(ev["text"])
                yield {"event": "token", "data": {"content": ev["text"]}}
            elif ev["type"] == "tool_calls":
                for tc in ev["tool_calls"]:
                    idx = tc.index
                    entry = tc_map.setdefault(
                        idx, {"id": None, "name": "", "arguments": ""}
                    )
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function and tc.function.name:
                        entry["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        entry["arguments"] += tc.function.arguments

        if tc_map:
            openai_tcs = []
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
            messages.append(
                {"role": "assistant", "content": None, "tool_calls": openai_tcs}
            )
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
                tool_calls_log.append(
                    {"name": name, "arguments": args, "result": str(result)}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": entry["id"],
                        "content": str(result),
                    }
                )
            continue

        # Final answer (no tool calls this step)
        final = "".join(content_parts)
        elapsed = int((time.monotonic() - start) * 1000)
        in_tok = _estimate_tokens(json.dumps(messages, ensure_ascii=False))
        out_tok = _estimate_tokens(final)
        cost = LLMClient.estimate_cost(
            model, {"input_tokens": in_tok, "output_tokens": out_tok}
        )
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
            )
        db.add(
            UsageEvent(
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
    session_id: Optional[str] = None,
) -> AsyncIterator[dict[str, Any]]:
    async for ev in _agent_stream(agent, message, db, 0, session_id):
        yield ev


async def run_agent_loop(
    agent: Agent,
    message: str,
    db: AsyncSession,
    depth: int = 0,
    session_id: Optional[str] = None,
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
