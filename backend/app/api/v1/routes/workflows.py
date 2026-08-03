from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.core.quota.dependencies import agent_run_admission, enforce_resource_quota
from app.core.workflow.engine import run_workflow
from app.dependencies import get_current_org_id, get_db, require_permission
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow import (
    RunWorkflowRequest,
    WorkflowCreate,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    WorkflowOut,
    WorkflowUpdate,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(
    prefix="/api/workflows",
    tags=["workflows"],
)


@router.get("", response_model=list[WorkflowOut], dependencies=[Depends(require_permission("workflows:read"))])
async def list_workflows(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    return await WorkflowService(db).list(org_id)


@router.post(
    "",
    response_model=WorkflowOut,
    status_code=201,
    dependencies=[
        Depends(require_permission("workflows:create")),
        Depends(enforce_resource_quota("workflows")),
    ],
)
async def create_workflow(
    body: WorkflowCreate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WorkflowService(db).create(org_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post(
    "/generate",
    response_model=WorkflowGenerateResponse,
    dependencies=[Depends(require_permission("workflows:create"))],
)
async def generate_workflow(
    body: WorkflowGenerateRequest,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WorkflowService(db).generate_graph(org_id, body.prompt, body.model_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=WorkflowOut, dependencies=[Depends(require_permission("workflows:read"))])
async def get_workflow(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    wf = await WorkflowService(db).get(org_id, id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    return wf


@router.put("/{id}", response_model=WorkflowOut, dependencies=[Depends(require_permission("workflows:update"))])
async def update_workflow(
    id: str,
    body: WorkflowUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WorkflowService(db).update(org_id, id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}", dependencies=[Depends(require_permission("workflows:delete"))])
async def delete_workflow(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    if not await WorkflowService(db).delete(org_id, id):
        raise HTTPException(404, "workflow not found")
    return {"ok": True}


@router.post(
    "/{id}/run",
    dependencies=[
        Depends(require_permission("workflows:run")),
        Depends(agent_run_admission),
    ],
)
async def run_workflow_endpoint(
    id: str,
    body: RunWorkflowRequest,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    wf = await WorkflowService(db).get(org_id, id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    if not body.stream:
        output, log, workflow_run_id = await run_workflow(wf, body.input, db, stream=False)
        return {"workflow_run_id": workflow_run_id, "output": output, "events": log}

    async def gen():
        async for ev in await run_workflow(wf, body.input, db, stream=True):
            yield format_sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post(
    "/runs/{run_id}/replay",
    dependencies=[Depends(require_permission("workflows:run"))],
)
async def replay_workflow_run(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Re-run a finished run against its recorded tool results.

    Deliberately not behind agent_run_admission: a replay executes no tools
    and makes no provider calls, so charging it against the run quota would
    penalise debugging.
    """
    res = await db.execute(
        select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.org_id == org_id)
    )
    source = res.scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "workflow run not found")

    wf = await WorkflowService(db).get(org_id, source.workflow_id)
    if wf is None:
        raise HTTPException(404, "workflow not found")

    output, log, replay_run_id = await run_workflow(
        wf,
        (source.input or {}).get("text", ""),
        db,
        stream=False,
        force_inline=True,
        replay_of_run_id=source.id,
    )
    # A replay that took a different path is a real finding, not an error:
    # report it with the divergence point so the caller can see where.
    diverged = next((e for e in log if e["event"] == "replay_diverged"), None)
    return {
        "workflow_run_id": replay_run_id,
        "source_run_id": source.id,
        "output": output,
        "diverged": diverged["data"] if diverged else None,
        "events": log,
    }


@router.get("/runs/{run_id}", dependencies=[Depends(require_permission("workflows:read"))])
async def get_workflow_run(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.org_id == org_id)
    )
    run = res.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "workflow run not found")
    node_res = await db.execute(
        select(WorkflowNodeRun)
        .where(WorkflowNodeRun.workflow_run_id == run.id)
        .order_by(WorkflowNodeRun.started_at, WorkflowNodeRun.attempt)
    )
    nodes = list(node_res.scalars().all())
    return {
        "id": run.id,
        "org_id": run.org_id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "input": run.input,
        "output": run.output,
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "nodes": [
            {
                "id": node.id,
                "node_id": node.node_id,
                "status": node.status,
                "attempt": node.attempt,
                "input": node.input,
                "output": node.output,
                "error": node.error,
                "started_at": node.started_at,
                "finished_at": node.finished_at,
            }
            for node in nodes
        ],
    }
