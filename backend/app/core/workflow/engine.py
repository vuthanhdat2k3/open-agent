from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from simpleeval import simple_eval
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.guardrails.approval import request_approval
from app.core.guardrails.budget import BudgetTracker, RunBudget
from app.core.tools.registry import BUILTIN_TOOLS, execute_tool_call
from app.core.tools.types import ToolContext
from app.mcp.client import build_mcp_tool_spec
from app.models.agent import Agent


def _eval_condition(cond: str, output: str) -> bool:
    try:
        return bool(simple_eval(cond, names={"output": output}, functions={}))
    except Exception:  # noqa: BLE001
        return False


class WorkflowWaitingApproval(RuntimeError):
    def __init__(self, approval_id: str) -> None:
        super().__init__("workflow waiting for approval")
        self.approval_id = approval_id


async def run_workflow_events(
    workflow: Any, input_text: str, db: AsyncSession
) -> AsyncIterator[dict[str, Any]]:
    graph = workflow.graph or {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        yield {"event": "error", "data": {"message": "workflow has no nodes"}}
        return

    node_by_id = {n["id"]: n for n in nodes}
    edges_from: dict[str, list[dict[str, Any]]] = {n["id"]: [] for n in nodes}
    edges_to: dict[str, list[dict[str, Any]]] = {n["id"]: [] for n in nodes}
    for e in edges:
        edges_from.setdefault(e["from_"], []).append(e)
        edges_to.setdefault(e["to"], []).append(e)

    input_nodes = [n for n in nodes if n["kind"] == "input"]
    if len(input_nodes) != 1:
        yield {
            "event": "error",
            "data": {"message": "workflow must have exactly one input node"},
        }
        return

    status: dict[str, str] = {n["id"]: "pending" for n in nodes}
    outputs: dict[str, str] = {}
    active_edges: set[Any] = set()
    settings = get_settings()
    budget = BudgetTracker(
        RunBudget(
            max_tool_calls=settings.budget_max_tool_calls,
            max_cost_usd=settings.budget_max_cost_usd,
            max_wall_seconds=settings.budget_max_wall_seconds,
            max_repeated_call=settings.budget_max_repeated_call,
        )
    )

    async def run_node(node: dict[str, Any]) -> str:
        kind = node["kind"]
        incoming = [e for e in edges_to[node["id"]] if e in active_edges]
        inputs = {e["from_"]: outputs.get(e["from_"], "") for e in incoming}

        if kind == "input":
            return input_text
        if kind == "merge":
            vals = list(inputs.values())
            if node.get("merge_mode") == "any":
                for v in vals:
                    if v:
                        return v
                return ""
            return "\n\n".join(vals)
        if kind == "output":
            return "\n\n".join(inputs.values())
        if kind == "tool":
            cfg = node.get("config", {}) or {}
            tool_name = cfg.get("tool")
            if not tool_name:
                raise RuntimeError("tool node missing 'tool' in config")
            args = {k: v for k, v in cfg.items() if k != "tool"}
            spec = BUILTIN_TOOLS.get(tool_name)
            if spec is None:
                spec = await build_mcp_tool_spec(tool_name, db, org_id=workflow.org_id)
            if spec is None:
                raise RuntimeError(f"tool '{tool_name}' not found")
            budget_reason = budget.record_call(tool_name, args)
            if budget_reason:
                raise RuntimeError(f"workflow budget exceeded: {budget_reason}")
            ctx = ToolContext(
                db=db,
                depth=0,
                workspace_dir=settings.workspace_dir,
                org_id=workflow.org_id,
                user_id=workflow.created_by_user_id,
            )
            return await execute_tool_call(spec, args, ctx)
        if kind == "approval":
            cfg = node.get("config", {}) or {}
            approval = await request_approval(
                db,
                org_id=workflow.org_id,
                run_type="workflow",
                run_id=workflow.id,
                node_id=node["id"],
                tool_name=cfg.get("tool_name"),
                args_snapshot=cfg,
                requested_by=workflow.created_by_user_id,
            )
            raise WorkflowWaitingApproval(approval.id)
        if kind == "agent":
            agent_id = node.get("agent_id")
            if not agent_id:
                raise RuntimeError("agent node missing agent_id")
            res = await db.execute(
                select(Agent).where(Agent.id == agent_id, Agent.org_id == workflow.org_id)
            )
            agent = res.scalar_one_or_none()
            if agent is None:
                raise RuntimeError(f"agent '{agent_id}' not found")
            from app.core.agent_loop import run_agent_loop

            text = "\n\n".join(inputs.values())
            loop = await run_agent_loop(agent, text, db, depth=0)
            return loop.content
        raise RuntimeError(f"unknown node kind {kind}")

    def is_ready(node: dict[str, Any]) -> bool:
        nid = node["id"]
        if status[nid] != "pending":
            return False
        if node["kind"] == "input":
            return True
        inc = [e for e in edges_to[nid] if e in active_edges]
        if not inc:
            return False
        if node.get("merge_mode") == "any":
            return any(status[e["from_"]] == "done" for e in inc)
        return all(status[e["from_"]] == "done" for e in inc)

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
        for n in ready:
            status[n["id"]] = "running"
            yield {
                "event": "node_start",
                "data": {"node_id": n["id"], "kind": n["kind"]},
            }
            tasks[n["id"]] = asyncio.create_task(run_node(n))

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for nid, res in zip(tasks.keys(), results, strict=False):
            if isinstance(res, WorkflowWaitingApproval):
                status[nid] = "waiting_approval"
                yield {
                    "event": "approval_required",
                    "data": {"node_id": nid, "approval_id": res.approval_id},
                }
                return
            if isinstance(res, Exception):
                status[nid] = "error"
                error_flag = True
                yield {
                    "event": "node_error",
                    "data": {"node_id": nid, "message": str(res)},
                }
                for e in edges_from[nid]:
                    active_edges.discard(e)
            else:
                status[nid] = "done"
                outputs[nid] = res
                yield {
                    "event": "node_done",
                    "data": {"node_id": nid, "output": res},
                }
                for e in edges_from[nid]:
                    cond = e.get("condition")
                    passed = _eval_condition(cond, res) if cond else True
                    if passed:
                        active_edges.add(e)
                        yield {
                            "event": "edge",
                            "data": {"from": e["from_"], "to": e["to"]},
                        }

    out_nodes = [n for n in nodes if n["kind"] == "output"]
    if out_nodes:
        final_output = "\n\n".join(outputs.get(n["id"], "") for n in out_nodes)
    else:
        done = [n for n in nodes if status[n["id"]] == "done"]
        final_output = outputs.get(done[-1]["id"], "") if done else ""
    yield {
        "event": "done",
        "data": {"output": final_output, "error": error_flag},
    }


async def run_workflow(
    workflow: Any,
    input_text: str,
    db: AsyncSession,
    stream: bool = False,
) -> Any:
    """If stream=True, returns the async generator of events.
    Otherwise awaits and returns (final_output, event_log)."""
    if stream:
        return run_workflow_events(workflow, input_text, db)
    final = ""
    log: list[dict[str, Any]] = []
    async for ev in run_workflow_events(workflow, input_text, db):
        log.append(ev)
        if ev["event"] == "done":
            final = ev["data"].get("output", final)
    return final, log
