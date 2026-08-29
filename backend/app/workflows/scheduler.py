from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workflow.schedule import to_schedule_dict
from app.db.base import gen_id, utc_now
from app.models.outbox import OutboxEvent
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_run import WorkflowRun
from app.models.workflow_trigger_state import WorkflowTriggerState

logger = structlog.get_logger(__name__)


def _local_now(now: datetime, timezone_name: str) -> datetime:
    aware = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    return aware.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)


def _field_matches(value: int, field: str, *, sunday: bool = False) -> bool:
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            base, step_text = part.split("/", 1)
            step = int(step_text)
            if step < 1:
                return False
            if base == "*":
                if value % step == 0:
                    return True
                continue
            part = base
        if "-" in part:
            start, end = (int(item) for item in part.split("-", 1))
            if start <= value <= end:
                return True
        elif part == "*" or int(part) == value or sunday and value == 6 and int(part) in {0, 7}:
            return True
    return False


def _start_of_next_month(dt: datetime) -> datetime:
    year = dt.year + (1 if dt.month == 12 else 0)
    month = 1 if dt.month == 12 else dt.month + 1
    return dt.replace(year=year, month=month, day=1, hour=0, minute=0)


def _next_custom_cron(cron: str, local: datetime) -> datetime:
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError("custom cron must be a 5-field expression")
    minute_f, hour_f, day_f, month_f, dow_f = fields
    candidate = local.replace(second=0, microsecond=0) + timedelta(minutes=1)
    # Bound the search to one year, but skip whole months/days/hours that
    # provably cannot match so a rare pattern (e.g. "0 2 29 2 *") resolves in
    # a handful of iterations instead of scanning ~527k minutes. Matching
    # semantics are unchanged: every field must still match (AND).
    deadline = candidate + timedelta(days=366)
    while candidate < deadline:
        if not _field_matches(candidate.month, month_f):
            candidate = _start_of_next_month(candidate)
            continue
        dow = (candidate.weekday() + 1) % 7
        if not (_field_matches(candidate.day, day_f) and _field_matches(dow, dow_f, sunday=True)):
            candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if not _field_matches(candidate.hour, hour_f):
            candidate = (candidate + timedelta(hours=1)).replace(minute=0)
            continue
        if not _field_matches(candidate.minute, minute_f):
            candidate += timedelta(minutes=1)
            continue
        return candidate
    raise ValueError("custom cron has no occurrence within one year")


def next_run_at(schedule: dict, timezone_name: str, *, now: datetime | None = None) -> datetime | None:
    """Return the next schedule occurrence as naive UTC."""
    current_utc = now or utc_now()
    local = _local_now(current_utc, timezone_name)
    start_date = _schedule_date(schedule.get("start_date"))
    end_date = _schedule_date(schedule.get("end_date"))
    if start_date and local.date() < start_date:
        local = datetime.combine(start_date, time.min) - timedelta(minutes=1)
    kind = schedule.get("kind", "daily")
    if kind in {"event", "once"}:
        return None
    if kind == "custom":
        candidate = _next_custom_cron(str(schedule.get("cron") or ""), local)
    elif kind == "hourly":
        interval = max(1, min(int(schedule.get("interval_hours") or 1), 12))
        candidate = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=interval)
    else:
        hour, minute = (int(part) for part in str(schedule.get("time") or "07:30").split(":", 1))
        candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local:
            candidate += timedelta(days=1)
        if kind == "weekdays":
            allowed = set(schedule.get("days_of_week") or ["mon", "tue", "wed", "thu", "fri"])
            while candidate.strftime("%a").lower()[:3] not in allowed:
                candidate += timedelta(days=1)
        elif kind == "weekly":
            allowed = schedule.get("days_of_week") or [schedule.get("weekday", 0)]
            numeric = {
                int(item) if isinstance(item, int) else ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(item)
                for item in allowed
            }
            while candidate.weekday() not in numeric:
                candidate += timedelta(days=1)
    if end_date and candidate.date() > end_date:
        return None
    return candidate.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc).replace(tzinfo=None)


def _schedule_date(value: object) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid schedule date: {value!r}") from exc


def _graph_hash(graph: dict) -> str:
    return hashlib.sha256(
        json.dumps(graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _scheduler_nodes(workflow: Workflow) -> dict[str, dict]:
    graph = workflow.graph or {}
    return {
        str(node["id"]): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("kind") == "scheduler" and node.get("id")
    }


async def reconcile_trigger_states(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Rebuild scheduler state from graph definitions without changing graphs."""
    current = now or utc_now()
    workflows = list((await db.scalars(select(Workflow))).all())
    states = list((await db.scalars(select(WorkflowTriggerState))).all())
    # A marketplace installation owns the workflow it materialized. When the
    # user pauses or archives the installation, the graph still carries an
    # enabled scheduler node — without this gate the workflow keeps firing
    # (and burning tokens) behind the user's back. A workflow with no
    # installation is hand-built and unaffected.
    blocked_workflow_ids: set[str] = set()
    installation_rows = await db.execute(
        select(WorkflowInstallation.workflow_id, WorkflowInstallation.status)
    )
    for workflow_id, status in installation_rows.all():
        if status != "enabled":
            blocked_workflow_ids.add(workflow_id)
    by_key = {(state.workflow_id, state.node_id): state for state in states}
    desired: set[tuple[str, str]] = set()
    changed = 0
    for workflow in workflows:
        installation_blocked = workflow.id in blocked_workflow_ids
        for node_id, node in _scheduler_nodes(workflow).items():
            desired.add((workflow.id, node_id))
            parameters = dict(node.get("parameters") or node.get("config") or {})
            timezone_name = str(parameters.get("timezone") or "UTC")
            enabled = parameters.get("enabled", True) is not False and not installation_blocked
            try:
                schedule = to_schedule_dict(parameters)
                first_run_at = next_run_at(schedule, timezone_name, now=current) if enabled else None
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "workflow_scheduler_trigger_invalid",
                    workflow_id=workflow.id,
                    node_id=node_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                state = by_key.get((workflow.id, node_id))
                if state is not None:
                    state.enabled = False
                    state.next_run_at = None
                    state.version += 1
                    changed += 1
                continue
            schedule_hash = _graph_hash({"schedule": schedule, "timezone": timezone_name})
            state = by_key.get((workflow.id, node_id))
            if state is None:
                state = WorkflowTriggerState(
                    org_id=workflow.org_id,
                    workflow_id=workflow.id,
                    node_id=node_id,
                    trigger_type="scheduler",
                    schedule_hash=schedule_hash,
                    enabled=enabled,
                    next_run_at=first_run_at,
                    version=1,
                )
                db.add(state)
                changed += 1
            elif state.schedule_hash != schedule_hash or state.enabled != enabled:
                state.schedule_hash = schedule_hash
                state.enabled = enabled
                state.next_run_at = first_run_at
                state.version += 1
                changed += 1
    for state in states:
        if (state.workflow_id, state.node_id) not in desired and state.enabled:
            state.enabled = False
            state.next_run_at = None
            state.version += 1
            changed += 1
    await db.flush()
    return changed


async def run_due_workflows(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    current = now or utc_now()
    await reconcile_trigger_states(db, now=current)
    states = list(
        (
            await db.scalars(
                select(WorkflowTriggerState)
                .where(
                    WorkflowTriggerState.enabled.is_(True),
                    WorkflowTriggerState.next_run_at.is_not(None),
                    WorkflowTriggerState.next_run_at <= current,
                )
                .order_by(WorkflowTriggerState.next_run_at)
                .limit(100)
            )
        ).all()
    )
    queued = 0
    for state in states:
        state_id = state.id
        workflow_id = state.workflow_id
        node_id = state.node_id
        try:
            async with db.begin_nested():
                scheduled_for = state.next_run_at
                if scheduled_for is None:
                    continue
                workflow = await db.scalar(
                    select(Workflow).where(
                        Workflow.id == state.workflow_id, Workflow.org_id == state.org_id
                    )
                )
                if workflow is None:
                    state.enabled = False
                    state.next_run_at = None
                    continue
                node = _scheduler_nodes(workflow).get(state.node_id)
                if node is None:
                    state.enabled = False
                    state.next_run_at = None
                    continue
                parameters = dict(node.get("parameters") or node.get("config") or {})
                timezone_name = str(parameters.get("timezone") or "UTC")
                schedule = to_schedule_dict(parameters)
                occurrence_key = f"{workflow.org_id}:{workflow.id}:{state.node_id}:{scheduled_for.isoformat()}"
                existing = await db.scalar(
                    select(WorkflowRun.id).where(
                        WorkflowRun.trigger_occurrence_key == occurrence_key
                    )
                )
                if existing is None:
                    graph = copy.deepcopy(workflow.graph or {})
                    run = WorkflowRun(
                        org_id=workflow.org_id,
                        workflow_id=workflow.id,
                        status="queued",
                        input={"text": "", "timezone": timezone_name, "trigger": "scheduled"},
                        triggered_by_user_id=workflow.created_by_user_id,
                        graph_snapshot=graph,
                        graph_hash=_graph_hash(graph),
                        trigger_node_id=state.node_id,
                        trigger_type="scheduler",
                        trigger_occurrence_key=occurrence_key,
                    )
                    db.add(run)
                    await db.flush()
                    db.add(
                        OutboxEvent(
                            id=gen_id(),
                            event_type="workflow.run.requested",
                            aggregate_type="workflow_trigger",
                            aggregate_id=state.id,
                            org_id=workflow.org_id,
                            user_id=workflow.created_by_user_id,
                            correlation_id=run.id,
                            payload={"run_id": run.id, "trigger_node_id": state.node_id},
                            dedupe_key=f"scheduler:{occurrence_key}",
                        )
                    )
                    queued += 1
                state.last_run_at = scheduled_for
                state.next_run_at = next_run_at(schedule, timezone_name, now=current)
        except Exception as exc:  # noqa: BLE001
            await db.execute(
                update(WorkflowTriggerState)
                .where(WorkflowTriggerState.id == state_id)
                .values(enabled=False, next_run_at=None)
            )
            logger.error(
                "workflow_scheduler_trigger_failed",
                workflow_id=workflow_id,
                node_id=node_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    await db.commit()
    return {"due": len(states), "queued": queued}
