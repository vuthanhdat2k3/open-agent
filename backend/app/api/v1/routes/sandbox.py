from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.core.quota.dependencies import agent_run_admission
from app.core.tools.sandbox import stream_sandbox_execution
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.user import User
from app.services.workspace_service import finish_execution_record, start_execution_record

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


class SandboxRunRequest(BaseModel):
    language: str = Field(..., description="python or bash")
    code: str = Field(..., description="Code to execute")


@router.post(
    "/run",
    dependencies=[
        Depends(require_permission("tools:use:execute")),
        Depends(agent_run_admission),
    ],
)
async def run_sandbox(
    body: SandboxRunRequest,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lang = body.language.lower()
    if lang not in ("python", "bash"):
        # TODO: Add "node" / "javascript" support in the future when docker image is available
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{body.language}'. Supported languages: 'python', 'bash'",
        )

    execution = await start_execution_record(
        db,
        org_id=org_id,
        source="sandbox_api",
        language=lang,
        command=body.code[:4000],
        user_id=current_user.id,
    )

    async def gen() -> AsyncIterator[str]:
        output = ""
        exit_code: int | None = None
        error: str | None = None
        async for ev in stream_sandbox_execution(lang, body.code):
            if ev.get("event") == "stdout":
                output += str(ev.get("data", {}).get("line", ""))
            elif ev.get("event") == "exit":
                exit_code = int(ev.get("data", {}).get("code", 0))
            elif ev.get("event") == "error":
                error = str(ev.get("data", {}).get("message", "sandbox error"))
                output += error
            yield format_sse(ev)
        if error:
            await finish_execution_record(
                db,
                execution,
                status="timed_out" if "timed out" in error else "failed",
                output=output,
                error=error,
                exit_code=exit_code,
            )
        else:
            await finish_execution_record(
                db,
                execution,
                status="succeeded" if exit_code == 0 else "failed",
                output=output,
                exit_code=exit_code,
            )

    return StreamingResponse(gen(), media_type="text/event-stream")
