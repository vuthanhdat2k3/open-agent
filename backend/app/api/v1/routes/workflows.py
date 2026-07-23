from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.core.security import verify_api_key
from app.core.workflow.engine import run_workflow
from app.db.session import get_db
from app.schemas.workflow import (
    RunWorkflowRequest,
    WorkflowCreate,
    WorkflowOut,
    WorkflowUpdate,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(
    prefix="/api/workflows",
    tags=["workflows"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    return await WorkflowService(db).list()


@router.post("", response_model=WorkflowOut, status_code=201)
async def create_workflow(body: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await WorkflowService(db).create(body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=WorkflowOut)
async def get_workflow(id: str, db: AsyncSession = Depends(get_db)):
    wf = await WorkflowService(db).get(id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    return wf


@router.put("/{id}", response_model=WorkflowOut)
async def update_workflow(id: str, body: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await WorkflowService(db).update(id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{id}")
async def delete_workflow(id: str, db: AsyncSession = Depends(get_db)):
    if not await WorkflowService(db).delete(id):
        raise HTTPException(404, "workflow not found")
    return {"ok": True}


@router.post("/{id}/run")
async def run_workflow_endpoint(
    id: str, body: RunWorkflowRequest, db: AsyncSession = Depends(get_db)
):
    wf = await WorkflowService(db).get(id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    if not body.stream:
        output, log = await run_workflow(wf, body.input, db, stream=False)
        return {"output": output, "events": log}

    async def gen():
        async for ev in run_workflow(wf, body.input, db, stream=True):
            yield format_sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream")
