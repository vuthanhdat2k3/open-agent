from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.models.message import Message
from app.models.session import Session
from app.schemas.chat import ChatMessageOut, SessionOut

router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Session).order_by(Session.updated_at.desc()))
    return list(res.scalars().all())


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.position)
    )
    return list(res.scalars().all())


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Session).where(Session.id == session_id))
    s = res.scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "session not found")
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.delete(s)
    await db.commit()
    return {"ok": True, "id": session_id}
