from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.scope import scope_to_owner
from app.dependencies import get_current_org_id, get_db, require_permission
from app.models.memory import SessionMemory
from app.models.message import Message
from app.models.session import Session
from app.schemas.chat import ChatMessageOut, SessionOut

router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"],
)


@router.get("", response_model=list[SessionOut], dependencies=[Depends(require_permission("sessions:read"))])
async def list_sessions(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    stmt = scope_to_owner(
        select(Session).where(Session.org_id == org_id), db, Session.created_by_user_id
    ).order_by(Session.updated_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut], dependencies=[Depends(require_permission("sessions:read"))])
async def list_messages(
    session_id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    session_stmt = scope_to_owner(
        select(Session).where(Session.id == session_id, Session.org_id == org_id),
        db,
        Session.created_by_user_id,
    )
    if await db.scalar(session_stmt) is None:
        raise HTTPException(404, "session not found")
    stmt = scope_to_owner(
        select(Message)
        .join(Session, Session.id == Message.session_id)
        .where(Message.session_id == session_id, Message.org_id == org_id),
        db,
        Session.created_by_user_id,
    ).order_by(Message.position)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.delete("/{session_id}", dependencies=[Depends(require_permission("sessions:delete"))])
async def delete_session(
    session_id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    res = await db.execute(
        scope_to_owner(
            select(Session).where(Session.id == session_id, Session.org_id == org_id),
            db,
            Session.created_by_user_id,
        )
    )
    s = res.scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "session not found")
    await db.execute(
        delete(SessionMemory).where(
            SessionMemory.session_id == session_id, SessionMemory.org_id == org_id
        )
    )
    await db.execute(
        delete(Message).where(Message.session_id == session_id, Message.org_id == org_id)
    )
    await db.delete(s)
    await db.commit()
    return {"ok": True, "id": session_id}
