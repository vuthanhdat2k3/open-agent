import asyncio
from contextlib import aclosing

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import SSE_HEARTBEAT_SECONDS, format_sse
from app.core.quota.dependencies import agent_run_admission
from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

router = APIRouter(
    prefix="/api/chat",
    tags=["chat"],
)


@router.post(
    "",
    dependencies=[
        Depends(require_permission("agents:run")),
        Depends(agent_run_admission),
    ],
)
async def chat(
    body: ChatRequest, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    svc = ChatService(db)
    if not body.stream:
        result = await svc.run(org_id, body)
        return result.model_dump()

    async def gen():
        async with aclosing(svc.stream(org_id, body)) as stream:
            while True:
                try:
                    ev = await asyncio.wait_for(stream.__anext__(), timeout=SSE_HEARTBEAT_SECONDS)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield format_sse(ev)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
