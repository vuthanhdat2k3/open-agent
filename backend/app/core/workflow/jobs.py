from __future__ import annotations

from sqlalchemy import select

from app.core.workflow.engine import run_workflow as run_workflow_engine
from app.db.session import SessionLocal
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun


async def run_workflow(ctx, workflow_run_id: str) -> None:  # noqa: ARG001
    async with SessionLocal() as session:
        res = await session.execute(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id))
        workflow_run = res.scalar_one_or_none()
        if workflow_run is None:
            return
        if workflow_run.status == "succeeded":
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
        await run_workflow_engine(
            workflow,
            str((workflow_run.input or {}).get("text", "")),
            session,
            stream=False,
            workflow_run_id=workflow_run.id,
            force_inline=True,
        )
