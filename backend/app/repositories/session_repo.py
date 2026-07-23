from sqlalchemy import select

from app.models.session import Session
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    def __init__(self, db):
        super().__init__(Session, db)

    async def list_by_agent(self, org_id: str, agent_id: str) -> list[Session]:
        res = await self.db.execute(
            select(Session).where(Session.org_id == org_id, Session.agent_id == agent_id)
        )
        return list(res.scalars().all())
