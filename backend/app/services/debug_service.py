from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.repositories.usage_repo import UsageRepository


class DebugService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_sessions(self, org_id: str) -> list[dict[str, Any]]:
        if not org_id:
            raise TypeError("org_id is required")
        res = await self.db.execute(
            select(Session, User)
            .outerjoin(User, Session.created_by_user_id == User.id)
            .where(Session.org_id == org_id)
            .order_by(Session.updated_at.desc())
        )
        return [
            {
                "id": session.id,
                "agent_id": session.agent_id,
                "title": session.title,
                "created_by_user_id": session.created_by_user_id,
                "creator_email": user.email if user else None,
                "creator_name": user.display_name if user else None,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }
            for session, user in res.all()
        ]

    async def get_session_tree(self, org_id: str, session_id: str) -> dict[str, Any]:
        if not org_id:
            raise TypeError("org_id is required")
        res = await self.db.execute(
            select(Session, User)
            .outerjoin(User, Session.created_by_user_id == User.id)
            .where(Session.id == session_id, Session.org_id == org_id)
        )
        row = res.first()
        if row is None:
            raise ValueError("session not found")
        session, user = row
        res = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id, Message.org_id == org_id)
            .order_by(Message.position)
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
                "created_by_user_id": session.created_by_user_id,
                "creator_email": user.email if user else None,
                "creator_name": user.display_name if user else None,
            },
            "messages": messages,
        }

    async def usage_summary(self, org_id: str) -> list[dict[str, Any]]:
        if not org_id:
            raise TypeError("org_id is required")
        repo = UsageRepository(self.db)
        return await repo.summary(org_id)

    async def list_agents(self, org_id: str) -> list[Agent]:
        if not org_id:
            raise TypeError("org_id is required")
        res = await self.db.execute(select(Agent).where(Agent.org_id == org_id))
        return list(res.scalars().all())
