from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import ChannelConnection, ChannelMessage
from app.repositories.base import BaseRepository


class ChannelRepository(BaseRepository[ChannelConnection]):
    def __init__(self, db: AsyncSession):
        super().__init__(ChannelConnection, db)

    async def get_by_provider(
        self, org_id: str, provider: str, bot_username: str | None = None
    ) -> ChannelConnection | None:
        filters = [
            ChannelConnection.org_id == org_id,
            ChannelConnection.provider == provider,
        ]
        if bot_username:
            filters.append(ChannelConnection.bot_username == bot_username)
        res = await self.db.execute(select(ChannelConnection).where(*filters))
        return res.scalar_one_or_none()

    async def list_by_provider(
        self, org_id: str, provider: str | None = None
    ) -> list[ChannelConnection]:
        filters = [ChannelConnection.org_id == org_id]
        if provider:
            filters.append(ChannelConnection.provider == provider)
        res = await self.db.execute(
            select(ChannelConnection)
            .where(*filters)
            .order_by(ChannelConnection.created_at.desc())
        )
        return list(res.scalars().all())


class ChannelMessageRepository(BaseRepository[ChannelMessage]):
    def __init__(self, db: AsyncSession):
        super().__init__(ChannelMessage, db)

    async def list_conversation(
        self,
        org_id: str,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChannelMessage]:
        res = await self.db.execute(
            select(ChannelMessage)
            .where(
                ChannelMessage.org_id == org_id,
                ChannelMessage.conversation_id == conversation_id,
            )
            .order_by(ChannelMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def list_by_connection(
        self,
        org_id: str,
        connection_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChannelMessage]:
        res = await self.db.execute(
            select(ChannelMessage)
            .where(
                ChannelMessage.org_id == org_id,
                ChannelMessage.connection_id == connection_id,
            )
            .order_by(ChannelMessage.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())
