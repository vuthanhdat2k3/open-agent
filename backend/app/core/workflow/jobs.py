from __future__ import annotations

from sqlalchemy import select, update

from app.core.agent_loop import await_deferred_user_write, fail_chat_run
from app.core.workflow.engine import run_workflow as run_workflow_engine
from app.db.session import SessionLocal
from app.models.task import Task
from app.models.workflow import Workflow
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
