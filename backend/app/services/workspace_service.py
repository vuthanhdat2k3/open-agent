from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.authz.scope import scope_to_owner
from app.db.base import utc_now
from app.models.workspace import SandboxExecution, WorkspaceArtifact

MAX_ARTIFACT_CONTENT_CHARS = 200_000
MAX_EXECUTION_PREVIEW_CHARS = 50_000


def _relative_workspace_path(workspace_dir: str, target: Path) -> str:
    base = Path(workspace_dir).resolve()
    return target.resolve().relative_to(base).as_posix()


def _safe_resolve(workspace_dir: str, path: str) -> Path | None:
    base = os.path.abspath(workspace_dir)
    target = os.path.abspath(os.path.join(base, path))
    if target != base and not target.startswith(base + os.sep):
        return None
    return Path(target)


def artifact_out(record: WorkspaceArtifact) -> dict[str, Any]:
    target = _safe_resolve(get_settings().workspace_dir, record.path)
    return {
        "id": record.id,
        "path": record.path,
        "content_type": record.content_type,
        "size": record.size,
        "sha256": record.sha256,
        "source_tool": record.source_tool,
        "agent_id": record.agent_id,
        "session_id": record.session_id,
        "task_id": record.task_id,
        "root_run_id": record.root_run_id,
        "exists": bool(target and target.is_file()),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


class WorkspaceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def list_artifacts(self, org_id: str) -> list[dict[str, Any]]:
        stmt = scope_to_owner(
            select(WorkspaceArtifact).where(WorkspaceArtifact.org_id == org_id),
            self.db,
            WorkspaceArtifact.created_by_user_id,
        )
        res = await self.db.execute(stmt.order_by(WorkspaceArtifact.updated_at.desc()))
        return [artifact_out(row) for row in res.scalars().all()]

    async def get_artifact(self, org_id: str, artifact_id: str) -> WorkspaceArtifact | None:
        stmt = scope_to_owner(
            select(WorkspaceArtifact).where(
                WorkspaceArtifact.id == artifact_id,
                WorkspaceArtifact.org_id == org_id,
            ),
            self.db,
            WorkspaceArtifact.created_by_user_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def artifact_path(self, org_id: str, artifact_id: str) -> Path:
        record = await self.get_artifact(org_id, artifact_id)
        if record is None:
            raise ValueError("artifact not found")
        target = _safe_resolve(self.settings.workspace_dir, record.path)
        if target is None:
            raise ValueError("artifact path escapes workspace")
        if not target.is_file():
            raise FileNotFoundError("artifact file not found on disk")
        return target

    async def read_artifact(self, org_id: str, artifact_id: str) -> str:
        target = await self.artifact_path(org_id, artifact_id)
        data = target.read_text(encoding="utf-8", errors="replace")
        if len(data) > MAX_ARTIFACT_CONTENT_CHARS:
            return data[:MAX_ARTIFACT_CONTENT_CHARS] + "\n...[truncated]"
        return data

    async def delete_artifact(self, org_id: str, artifact_id: str) -> bool:
        record = await self.get_artifact(org_id, artifact_id)
        if record is None:
            return False
        target = _safe_resolve(self.settings.workspace_dir, record.path)
        if target and target.is_file():
            target.unlink()
        await self.db.delete(record)
        await self.db.commit()
        return True

    async def list_executions(self, org_id: str) -> list[SandboxExecution]:
        stmt = scope_to_owner(
            select(SandboxExecution).where(SandboxExecution.org_id == org_id),
            self.db,
            SandboxExecution.created_by_user_id,
        )
        res = await self.db.execute(
            stmt.order_by(SandboxExecution.started_at.desc()).limit(200)
        )
        return list(res.scalars().all())

    async def get_execution(self, org_id: str, execution_id: str) -> SandboxExecution | None:
        stmt = scope_to_owner(
            select(SandboxExecution).where(
                SandboxExecution.id == execution_id,
                SandboxExecution.org_id == org_id,
            ),
            self.db,
            SandboxExecution.created_by_user_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_execution(self, org_id: str, execution_id: str) -> bool:
        record = await self.get_execution(org_id, execution_id)
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.commit()
        return True


async def upsert_workspace_artifact(
    db: AsyncSession | None,
    *,
    org_id: str | None,
    path: Path,
    workspace_dir: str,
    source_tool: str,
    user_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    root_run_id: str | None = None,
) -> None:
    if db is None or not org_id:
        return
    rel_path = _relative_workspace_path(workspace_dir, path)
    data = path.read_bytes()
    content_type = mimetypes.guess_type(rel_path)[0] or "text/plain"
    sha = hashlib.sha256(data).hexdigest()
    res = await db.execute(
        select(WorkspaceArtifact).where(
            WorkspaceArtifact.org_id == org_id,
            WorkspaceArtifact.path == rel_path,
        )
    )
    record = res.scalar_one_or_none()
    if record is None:
        record = WorkspaceArtifact(
            org_id=org_id,
            created_by_user_id=user_id,
            path=rel_path,
        )
        db.add(record)
    record.agent_id = agent_id
    record.session_id = session_id
    record.task_id = task_id
    record.root_run_id = root_run_id
    record.source_tool = source_tool
    record.content_type = content_type
    record.size = len(data)
    record.sha256 = sha
    record.updated_at = utc_now()
    try:
        await db.commit()
    except Exception:
        await db.rollback()


async def start_execution_record(
    db: AsyncSession | None,
    *,
    org_id: str | None,
    source: str,
    language: str = "",
    command: str = "",
    user_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    root_run_id: str | None = None,
) -> SandboxExecution | None:
    if db is None or not org_id:
        return None
    record = SandboxExecution(
        org_id=org_id,
        created_by_user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
        task_id=task_id,
        root_run_id=root_run_id,
        source=source,
        language=language,
        command=command,
        status="running",
        started_at=utc_now(),
    )
    try:
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record
    except Exception:
        await db.rollback()
        return None


async def finish_execution_record(
    db: AsyncSession | None,
    record: SandboxExecution | None,
    *,
    status: str,
    output: str = "",
    error: str | None = None,
    exit_code: int | None = None,
) -> None:
    if db is None or record is None:
        return
    now = utc_now()
    started = record.started_at
    record.status = status
    record.exit_code = exit_code
    record.finished_at = now
    record.duration_ms = int((now - started).total_seconds() * 1000)
    record.stdout_preview = output[:MAX_EXECUTION_PREVIEW_CHARS]
    record.error = error
    try:
        await db.commit()
    except Exception:
        await db.rollback()
