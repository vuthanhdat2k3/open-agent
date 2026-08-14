from __future__ import annotations

from sqlalchemy import select, update

from app.core.agent_loop import await_deferred_user_write, fail_chat_run
from app.core.workflow.engine import run_workflow as run_workflow_engine
from app.db.base import utc_now
from app.db.session import SessionLocal
from app.models.task import Task
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_occurrence import WorkflowOccurrence
from app.models.workflow_run import WorkflowRun
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


async def run_workflow(ctx, workflow_run_id: str) -> None:  # noqa: ARG001
    async with SessionLocal() as session:
        res = await session.execute(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id))
        workflow_run = res.scalar_one_or_none()
        if workflow_run is None or workflow_run.status == "succeeded":
            return
        wf_res = await session.execute(
            select(Workflow).where(
                Workflow.id == workflow_run.workflow_id,
                Workflow.org_id == workflow_run.org_id,
            )
        )
        workflow = wf_res.scalar_one_or_none()
        if workflow is None:
            workflow_run.status = "failed"
            workflow_run.error = "workflow not found"
            await session.commit()
            return
        try:
            template_key = str((workflow_run.input or {}).get("template_key") or "")
            installation_id = str((workflow_run.input or {}).get("installation_id") or "")
            if template_key and installation_id:
                installation = await session.scalar(
                    select(WorkflowInstallation).where(
                        WorkflowInstallation.id == installation_id,
                        WorkflowInstallation.org_id == workflow_run.org_id,
                        WorkflowInstallation.workflow_id == workflow.id,
                    )
                )
                if installation is None or installation.status == "archived":
                    raise RuntimeError("workflow installation is no longer active")
                if template_key == "gmail_monitor_and_triage":
                    from app.customer_intelligence.ingest import sync_connection

                    connection_id = str((installation.settings or {}).get("connection_id") or "")
                    if not connection_id:
                        raise RuntimeError("Gmail monitor has no connection binding")
                    result = await sync_connection(
                        session,
                        org_id=workflow_run.org_id,
                        connection_id=connection_id,
                        trigger=str((workflow_run.input or {}).get("trigger") or "scheduled"),
                        actor_user_id=workflow_run.triggered_by_user_id,
                    )
                    workflow_run.output = {
                        "kind": "catalog_execution",
                        "template_key": template_key,
                        "result": result,
                    }
                    workflow_run.status = "succeeded"
                    workflow_run.finished_at = utc_now()
                    occurrence_id = (workflow_run.input or {}).get("occurrence_id")
                    if occurrence_id:
                        occurrence = await session.get(WorkflowOccurrence, occurrence_id)
                        if occurrence is not None:
                            occurrence.status = "succeeded"
                    await session.commit()
                    return
                raise RuntimeError(f"template executor is not implemented: {template_key}")
            await run_workflow_engine(
                workflow,
                str((workflow_run.input or {}).get("text", "")),
                session,
                stream=False,
                workflow_run_id=workflow_run.id,
                force_inline=True,
                user_id=workflow_run.triggered_by_user_id,
                timezone_name=(workflow_run.input or {}).get("timezone"),
            )
        except Exception as exc:  # noqa: BLE001
            workflow_run.status = "failed"
            workflow_run.error = str(exc)
            workflow_run.finished_at = utc_now()
            occurrence_id = (workflow_run.input or {}).get("occurrence_id")
            if occurrence_id:
                occurrence = await session.get(WorkflowOccurrence, occurrence_id)
                if occurrence is not None:
                    occurrence.status = "failed"
            await session.commit()


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
