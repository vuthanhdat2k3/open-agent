from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import PrincipalContext
from app.core.authz.scope import scope_to_owner
from app.core.execution_policy import ExecutionPolicy, normalize_execution_policy
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.memory import SessionMemory
from app.models.message import Message
from app.models.session import Session
from app.models.session_event import SessionEvent
from app.models.user import User
from app.schemas.chat import ChatMessageOut, SessionOut, SessionUpdate

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


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("sessions:write")),
    db: AsyncSession = Depends(get_db),
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
    if payload.execution_policy is not None:
        new_policy = normalize_execution_policy(payload.execution_policy)
        user_role = (
            authz.role.value if hasattr(authz.role, "value") else str(authz.role)
        ) if authz and authz.role else getattr(user, "role", None)
        if new_policy is ExecutionPolicy.full_access and user_role not in {
            "user",
            "operator",
            "org_admin",
            "platform_admin",
        }:
            raise HTTPException(403, "full-access execution policy is not available for this role")
        s.execution_policy = new_policy.value
    if payload.title is not None:
        s.title = payload.title
    await db.commit()
    await db.refresh(s)
    return s


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
    await db.execute(
        delete(SessionEvent).where(
            SessionEvent.session_id == session_id, SessionEvent.org_id == org_id
        )
    )
    await db.delete(s)
    await db.commit()
    return {"ok": True, "id": session_id}
