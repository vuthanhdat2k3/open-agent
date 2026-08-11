from __future__ import annotations

import asyncio
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


def _eval_condition(cond: str, output: str) -> bool:
    try:
        return bool(simple_eval(cond, names={"output": output}, functions={}))
    except Exception:  # noqa: BLE001
        return False


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
        input={"text": input_text},
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
) -> AsyncIterator[dict[str, Any]]:
    settings = get_settings()
    workflow_run = await create_workflow_run(
        workflow, input_text, db, workflow_run_id, user_id
    )
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

    input_nodes = [n for n in nodes if n["kind"] == "input"]
    if len(input_nodes) != 1:
        workflow_run.status = "failed"
        workflow_run.error = "workflow must have exactly one input node"
        workflow_run.finished_at = utc_now()
        await db.commit()
        await resume.release_lease(db, workflow_run.id)
        yield {
            "event": "error",
            "data": {"message": "workflow must have exactly one input node"},
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
            outputs[node_id] = resumed_outputs[node_id]
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
    ) -> str:
        kind = node.get("kind") or node.get("type")
        incoming = [e for e in edges_to[node["id"]] if e["_idx"] in active_edges]
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
            args = {k: v for k, v in cfg.items() if k not in {"tool", "retry", "timeout_s"}}
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
                return replayed

            ctx = ToolContext(
                db=db,
                depth=0,
                workspace_dir=settings.workspace_dir,
                org_id=workflow.org_id,
                user_id=actor_user_id,
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
            return result
        if kind == "approval":
            cfg = node.get("config", {}) or {}
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
            cfg = node.get("config", {}) or {}
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
            child_input = "\n\n".join(inputs.values())
            child_output, _child_log, _child_run_id = await run_workflow(
                child,
                child_input,
                db,
                stream=False,
                force_inline=True,
                user_id=actor_user_id,
            )
            return child_output
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
            node_run.agent_release_id = agent.active_release_id
            await db.commit()
            from app.core.agent_loop import run_agent_loop

            text = "\n\n".join(inputs.values())
            loop = await run_agent_loop(
                agent,
                text,
                db,
                depth=0,
                root_run_id=workflow_run.id,
                replay_cursor=replay_cursor,
                user_id=actor_user_id,
            )
            return loop.content
        raise RuntimeError(f"unknown node kind {kind}")

    async def run_node(node: dict[str, Any], db: AsyncSession) -> str:
        cfg = node.get("config", {}) or {}
        retry_cfg = node.get("retry") or cfg.get("retry") or {}
        max_attempts = max(1, int(retry_cfg.get("max_attempts", 1) or 1))
        backoff_s = max(0.0, float(retry_cfg.get("backoff_s", 0.0) or 0.0))
        timeout_s = node.get("timeout_s") or cfg.get("timeout_s")

        # Resume: a node that already succeeded in an earlier attempt of this
        # run is not executed again — its recorded output is replayed. This
        # makes a crashed multi-hour workflow cheap to restart, and stops
        # side-effecting tool nodes from firing twice.
        if node["id"] in resumed_outputs:
            return resumed_outputs[node["id"]]

        last_error: Exception | None = None
        incoming = [e for e in edges_to[node["id"]] if e["_idx"] in active_edges]
        node_input = {"inputs": {e["from_"]: outputs.get(e["from_"], "") for e in incoming}}
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
            await _finish_node_run(db, node_run, status="succeeded", output={"text": result})
            return result
        raise RuntimeError(str(last_error) if last_error else "node failed")

    async def run_node_in_new_session(
        node: dict[str, Any], session_factory: async_sessionmaker[AsyncSession]
    ) -> str:
        async with session_factory() as node_db:
            return await run_node(node, node_db)

    def is_ready(node: dict[str, Any]) -> bool:
        nid = node["id"]
        if status[nid] != "pending":
            return False
        if node["kind"] == "input":
            return True
        inc = [e for e in edges_to[nid] if e["_idx"] in active_edges]
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
            coro = (
                run_node_in_new_session(n, node_sessionmaker)
                if fan_out
                else run_node(n, db)
            )
            tasks[n["id"]] = asyncio.create_task(coro)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        # Heartbeat between scheduling rounds: a workflow whose nodes take
        # longer than the lease TTL would otherwise look abandoned and get
        # picked up by another worker while it is still running.
        await resume.extend_lease(db, workflow_run.id)
        for nid, res in zip(tasks.keys(), results, strict=False):
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
                    "data": {"node_id": nid, "output": res},
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
        final_output = "\n\n".join(outputs.get(n["id"], "") for n in out_nodes)
    else:
        done = [n for n in nodes if status[n["id"]] == "done"]
        final_output = outputs.get(done[-1]["id"], "") if done else ""
    yield {
        "event": "done",
        "data": {"output": final_output, "error": error_flag},
    }
    workflow_run.status = "failed" if error_flag else "succeeded"
    workflow_run.output = {"text": final_output}
    workflow_run.finished_at = utc_now()
    await db.commit()
    await resume.release_lease(db, workflow_run.id)
    workflow_run_duration_seconds.observe(
        max(0.0, time.monotonic() - budget.started_at)
    )


async def run_workflow_events(
    workflow: Any,
    input_text: str,
    db: AsyncSession,
    workflow_run_id: str | None = None,
    force_inline: bool = False,
    replay_of_run_id: str | None = None,
    user_id: str | None = None,
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
    ):
        log.append(ev)
        if ev["event"] == "workflow_start":
            workflow_run_id_seen = ev["data"]["workflow_run_id"]
        if ev["event"] == "done":
            final = ev["data"].get("output", final)
    return final, log, workflow_run_id_seen
