from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.v1.sse import format_sse
from app.core.quota.dependencies import agent_run_admission
from app.core.tools.sandbox import stream_sandbox_execution
from app.dependencies import require_permission

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
async def run_sandbox(body: SandboxRunRequest):
    lang = body.language.lower()
    if lang not in ("python", "bash"):
        # TODO: Add "node" / "javascript" support in the future when docker image is available
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{body.language}'. Supported languages: 'python', 'bash'",
        )

    async def gen() -> AsyncIterator[str]:
        async for ev in stream_sandbox_execution(lang, body.code):
            yield format_sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream")
