from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkspaceArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    path: str
    content_type: str
    size: int
    sha256: str
    source_tool: str
    agent_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    root_run_id: str | None = None
    exists: bool = True
    created_at: datetime
    updated_at: datetime


class SandboxExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    language: str
    command: str
    status: str
    exit_code: int | None = None
    duration_ms: int | None = None
    stdout_preview: str
    error: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    root_run_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime
