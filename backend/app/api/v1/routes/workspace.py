from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.workspace import SandboxExecutionOut, WorkspaceArtifactOut
from app.services.workspace_service import WorkspaceService, artifact_out

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get(
    "/artifacts",
    response_model=list[WorkspaceArtifactOut],
    dependencies=[Depends(require_permission("files:read"))],
)
async def list_artifacts(
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    return await WorkspaceService(db).list_artifacts(org_id)


@router.get(
    "/artifacts/{artifact_id}",
    response_model=WorkspaceArtifactOut,
    dependencies=[Depends(require_permission("files:read"))],
)
async def get_artifact(
    artifact_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    record = await WorkspaceService(db).get_artifact(org_id, artifact_id)
    if record is None:
        raise HTTPException(404, "artifact not found")
    return artifact_out(record)


@router.get(
    "/artifacts/{artifact_id}/content",
    dependencies=[Depends(require_permission("files:read"))],
)
async def read_artifact(
    artifact_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return PlainTextResponse(await WorkspaceService(db).read_artifact(org_id, artifact_id))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get(
    "/artifacts/{artifact_id}/download",
    dependencies=[Depends(require_permission("files:read"))],
)
async def download_artifact(
    artifact_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        target = await WorkspaceService(db).artifact_path(org_id, artifact_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(target, filename=target.name)


@router.delete(
    "/artifacts/{artifact_id}",
    dependencies=[Depends(require_permission("files:manage"))],
)
async def delete_artifact(
    artifact_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    if not await WorkspaceService(db).delete_artifact(org_id, artifact_id):
        raise HTTPException(404, "artifact not found")
    return {"ok": True}

@router.get(
    "/executions",
    response_model=list[SandboxExecutionOut],
    dependencies=[Depends(require_permission("usage:read"))],
)
async def list_executions(
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    return await WorkspaceService(db).list_executions(org_id)


@router.get(
    "/executions/{execution_id}",
    response_model=SandboxExecutionOut,
    dependencies=[Depends(require_permission("usage:read"))],
)
async def get_execution(
    execution_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    record = await WorkspaceService(db).get_execution(org_id, execution_id)
    if record is None:
        raise HTTPException(404, "execution not found")
    return record


@router.delete(
    "/executions/{execution_id}",
    dependencies=[Depends(require_permission("usage:read"))],
)
async def delete_execution(
    execution_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    if not await WorkspaceService(db).delete_execution(org_id, execution_id):
        raise HTTPException(404, "execution not found")
    return {"ok": True}
