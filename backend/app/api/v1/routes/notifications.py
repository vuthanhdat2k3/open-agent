from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_current_user, get_db
from app.models.user import User
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    title: str
    body: str
    source_type: str
    source_id: str | None = None
    link_url: str | None = None
    read_at: datetime | None = None
    created_at: datetime


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    limit: int = 30,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await NotificationService(db).list(
        org_id, current_user.id, unread_only=unread_only, limit=limit
    )
    return items


@router.get("/unread-count")
async def unread_count(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await NotificationService(db).unread_count(org_id, current_user.id)
    return {"count": count}


@router.post("/{id}/read")
async def mark_notification_read(
    id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await NotificationService(db).mark_read(org_id, current_user.id, id)
    if not ok:
        raise HTTPException(404, "notification not found")
    return {"ok": True}


@router.post("/read-all")
async def mark_all_notifications_read(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await NotificationService(db).mark_all_read(org_id, current_user.id)
    return {"marked": count}
