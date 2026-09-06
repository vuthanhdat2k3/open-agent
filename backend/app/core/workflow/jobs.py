from __future__ import annotations

from sqlalchemy import select, update

from app.core.agent_loop import await_deferred_user_write, fail_chat_run
from app.core.workflow.engine import run_workflow as run_workflow_engine
from app.db.base import utc_now
from app.db.session import SessionLocal
from app.models.task import Task
from app.models.workflow import Workflow
from app.models.workflow_occurrence import WorkflowOccurrence
from app.models.workflow_run import WorkflowRun
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

_TERMINAL_STATUSES = {"succeeded", "failed", "diverged", "cancelled"}


async def _notify_run_finished(session, workflow: Workflow, workflow_run: WorkflowRun) -> None:
    """Notify the triggering user that a background run reached a terminal
    state. This is the only funnel every non-inline run (scheduled, queued
    from chat, or "run now" from the Workflows page) executes through, so a
    single hook here covers all of them — the run would otherwise finish
    unattended with no way for the user to learn about it short of manually
    opening the run history.
    """
    if workflow_run.status not in _TERMINAL_STATUSES or not workflow_run.triggered_by_user_id:
        return
    from app.services.notification_service import NotificationService

    if workflow_run.status == "succeeded":
        title = f"Workflow ‘{workflow.name}’ completed"
        output = workflow_run.output
        body = output.get("text") if isinstance(output, dict) else str(output or "")
    else:
        title = f"Workflow ‘{workflow.name}’ {workflow_run.status}"
        body = workflow_run.error or ""
    await NotificationService(session).create(
        org_id=workflow_run.org_id,
        user_id=workflow_run.triggered_by_user_id,
        title=title,
        body=(body or "")[:4000],
        source_type="workflow_run",
        source_id=workflow_run.id,
        link_url="/reports",
    )


async def run_workflow(ctx, workflow_run_id: str) -> None:  # noqa: ARG001
    """ARQ entry: execute a queued/resumed workflow run.

    Delegates to :func:`run_workflow_detached` so a resumed run can also be
    driven in-process (e.g. from an approval decision in inline mode) through
    the exact same code path.
    """
    await run_workflow_detached(workflow_run_id)


async def run_workflow_detached(workflow_run_id: str) -> None:
    """Execute a workflow run through its persisted graph.

    Catalog metadata may remain attached to a run for audit/backward
    compatibility, but it never selects an executor. The graph snapshot and
    trigger identity are the only execution inputs.
    """
    async with SessionLocal() as session:
        res = await session.execute(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id))
        workflow_run = res.scalar_one_or_none()
        if workflow_run is None or workflow_run.status in {
            "succeeded",
            "failed",
            "diverged",
            "cancelled",
        }:
            return
        workflow = await session.scalar(
            select(Workflow).where(
                Workflow.id == workflow_run.workflow_id,
                Workflow.org_id == workflow_run.org_id,
            )
        )
        if workflow is None:
            workflow_run.status = "failed"
            workflow_run.error = "workflow not found"
            await session.commit()
            return

        occurrence_id = (workflow_run.input or {}).get("occurrence_id")
        try:
            await run_workflow_engine(
                workflow,
                str((workflow_run.input or {}).get("text", "")),
                session,
                stream=False,
                workflow_run_id=workflow_run.id,
                force_inline=True,
                user_id=workflow_run.triggered_by_user_id,
                timezone_name=(workflow_run.input or {}).get("timezone"),
                trigger_node_id=workflow_run.trigger_node_id,
                trigger_type=workflow_run.trigger_type,
            )
            if occurrence_id:
                occurrence = await session.get(WorkflowOccurrence, occurrence_id)
                if occurrence is not None and workflow_run.status != "running":
                    occurrence.status = workflow_run.status
            await session.commit()
            await _notify_run_finished(session, workflow, workflow_run)
        except Exception as exc:  # noqa: BLE001
            workflow_run.status = "failed"
            workflow_run.error = str(exc)
            workflow_run.finished_at = utc_now()
            if occurrence_id:
                occurrence = await session.get(WorkflowOccurrence, occurrence_id)
                if occurrence is not None:
                    occurrence.status = "failed"
            await session.commit()
            await _notify_run_finished(session, workflow, workflow_run)


async def run_chat(ctx, payload: dict) -> None:  # noqa: ARG001
    async with SessionLocal() as session:
        request = ChatRequest.model_validate(payload)
        res = await session.execute(
            select(Task).where(Task.id == request.run_id, Task.org_id == payload["org_id"])
        )
        task = res.scalar_one_or_none()
        if task is None or task.status != "queued":
            return
        claimed = await session.execute(
            update(Task)
            .where(Task.id == task.id, Task.status == "queued")
            .values(status="running")
        )
        if claimed.rowcount != 1:
            return
        await session.commit()
        try:
            await ChatService(session).run(
                payload["org_id"],
                request,
                user_id=payload.get("user_id"),
                root_run_id=payload.get("root_run_id") or request.run_id,
                current_task_id=task.id,
                approval_resume_id=payload.get("approval_resume_id"),
                prepared=bool(payload.get("prepared")),
                prepared_agent_release_id=payload.get("prepared_agent_release_id"),
            )
        except Exception as exc:  # noqa: BLE001
            await fail_chat_run(session, task, exc)
        finally:
            await await_deferred_user_write(request.run_id)
