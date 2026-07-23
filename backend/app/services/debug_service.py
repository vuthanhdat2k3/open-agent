from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.message import Message
from app.models.session import Session
from app.repositories.usage_repo import UsageRepository


class DebugService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_sessions(self) -> list[Session]:
        res = await self.db.execute(select(Session).order_by(Session.updated_at.desc()))
        return list(res.scalars().all())

    async def get_session_tree(self, session_id: str) -> dict[str, Any]:
        res = await self.db.execute(select(Session).where(Session.id == session_id))
        session = res.scalar_one_or_none()
        if session is None:
            raise ValueError("session not found")
        res = await self.db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.position)
        )
        messages = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "meta": m.meta,
                "position": m.position,
            }
            for m in res.scalars().all()
        ]
        return {
            "session": {
                "id": session.id,
                "agent_id": session.agent_id,
                "title": session.title,
            },
            "messages": messages,
        }

    async def usage_summary(self) -> list[dict[str, Any]]:
        repo = UsageRepository(self.db)
        return await repo.summary()

    async def list_agents(self) -> list[Agent]:
        res = await self.db.execute(select(Agent))
        return list(res.scalars().all())
