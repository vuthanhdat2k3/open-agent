from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.notification import Notification


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        org_id: str,
        user_id: str,
        title: str,
        body: str = "",
        source_type: str = "generic",
        source_id: str | None = None,
        link_url: str | None = None,
    ) -> Notification:
        notification = Notification(
            org_id=org_id,
            user_id=user_id,
            title=title[:255],
            body=body,
            source_type=source_type,
            source_id=source_id,
            link_url=link_url,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def list(
        self, org_id: str, user_id: str, *, unread_only: bool = False, limit: int = 30
    ) -> list[Notification]:
        stmt = select(Notification).where(
            Notification.org_id == org_id, Notification.user_id == user_id
        )
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        stmt = stmt.order_by(Notification.created_at.desc()).limit(min(limit, 100))
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def unread_count(self, org_id: str, user_id: str) -> int:
        stmt = select(func.count()).select_from(Notification).where(
            Notification.org_id == org_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        return int(await self.db.scalar(stmt) or 0)

    async def mark_read(self, org_id: str, user_id: str, notification_id: str) -> bool:
        notification = await self.db.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.org_id == org_id,
                Notification.user_id == user_id,
            )
        )
        if notification is None:
            return False
        if notification.read_at is None:
            notification.read_at = utc_now()
            await self.db.commit()
        return True

    async def mark_all_read(self, org_id: str, user_id: str) -> int:
        unread = await self.list(org_id, user_id, unread_only=True, limit=1000)
        now = utc_now()
        for notification in unread:
            notification.read_at = now
        if unread:
            await self.db.commit()
        return len(unread)
