from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

router = APIRouter(
    prefix="/api/chat",
    tags=["chat"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    if not body.stream:
        result = await svc.run(body)
        return result.model_dump()

    async def gen():
        async for ev in svc.stream(body):
            yield format_sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream")
