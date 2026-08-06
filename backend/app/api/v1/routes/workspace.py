from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.config import get_settings
from app.core.tools import live_run
from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.workspace import (
    ActiveRunOut,
    SandboxExecutionOut,
    SandboxRunOut,
    WorkspaceArtifactOut,
)
from app.services.workspace_service import WorkspaceService, artifact_out

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

_LANG_BY_SUFFIX = {
    ".py": "python",
    ".sh": "bash",
}


def _infer_language(path: str) -> str | None:
    return _LANG_BY_SUFFIX.get(Path(path).suffix.lower())


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
    "/executions/active",
    response_model=ActiveRunOut | None,
    dependencies=[Depends(require_permission("files:read"))],
)
async def get_active_execution(
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    run = live_run.get_active_run(org_id)
    if run is None:
        return None
    if run.remaining_seconds() <= 0:
        await live_run.stop_live_run(org_id, reason="timeout")
        return None
    record = await WorkspaceService(db).get_execution(org_id, run.execution_id)
    return ActiveRunOut(
        id=run.execution_id,
        status=run.status,
        path=record.command if record else "",
        language=run.language,
        started_at=record.started_at if record else datetime.now(timezone.utc),
        remaining_seconds=run.remaining_seconds(),
        max_seconds=run.max_seconds,
    )


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


@router.post(
    "/artifacts/{artifact_id}/run",
    response_model=SandboxRunOut,
    status_code=202,
    dependencies=[Depends(require_permission("files:manage"))],
)
async def run_artifact(
    artifact_id: str,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    svc = WorkspaceService(db)
    try:
        target = await svc.artifact_path(org_id, artifact_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc

    language = _infer_language(str(target))
    if language is None:
        raise HTTPException(400, "unsupported artifact type (use .py or .sh)")

    try:
        live = await live_run.start_live_run(
            db,
            org_id=org_id,
            user_id=getattr(request.state, "user_id", None),
            artifact_id=artifact_id,
            workspace_dir=svc.settings.workspace_dir,
            language=language,
        )
    except live_run.RunAlreadyActive:
        raise HTTPException(409, "an execution is already running for this organization")

    return SandboxRunOut(
        execution_id=live.execution_id,
        artifact_id=artifact_id,
        max_seconds=float(get_settings().sandbox_max_run_seconds),
    )


@router.get(
    "/executions/{execution_id}/stream",
    dependencies=[Depends(require_permission("files:read"))],
)
async def stream_execution(
    execution_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    record = await WorkspaceService(db).get_execution(org_id, execution_id)
    if record is None:
        raise HTTPException(404, "execution not found")
    await db.close()

    async def _gen():
        run = live_run.get_active_run(org_id)
        if run is not None and run.execution_id == execution_id:
            async for ev in live_run.stream_live_run(org_id):
                yield format_sse(ev)
            return
        yield format_sse({"event": "stdout", "data": {"line": record.stdout_preview or ""}})
        if record.exit_code is not None:
            yield format_sse({"event": "exit", "data": {"code": record.exit_code}})

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post(
    "/executions/{execution_id}/stop",
    dependencies=[Depends(require_permission("files:manage"))],
)
async def stop_execution(
    execution_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    record = await WorkspaceService(db).get_execution(org_id, execution_id)
    if record is None:
        raise HTTPException(404, "execution not found")
    await db.close()
    await live_run.stop_live_run(org_id, reason="user")
    return {"ok": True}
