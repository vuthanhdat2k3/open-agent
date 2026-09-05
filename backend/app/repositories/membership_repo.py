from __future__ import annotations

from sqlalchemy import select

from app.models.membership import Membership
from app.repositories.base import BaseRepository


class MembershipRepository(BaseRepository[Membership]):
    def __init__(self, db):
        super().__init__(Membership, db)

    async def get_membership(self, org_id: str, user_id: str) -> Membership | None:
        """Return one of this user's role-rows in the org (a user may hold
        more than one - see Membership's (org_id, user_id, role) uniqueness).
        Use `list_by_org`/`list_by_user` when the full role set matters."""
        res = await self.db.execute(
            select(Membership)
            .where(Membership.org_id == org_id, Membership.user_id == user_id)
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def list_by_org(self, org_id: str) -> list[Membership]:
        res = await self.db.execute(select(Membership).where(Membership.org_id == org_id))
        return list(res.scalars().all())

    async def list_by_user(self, user_id: str) -> list[Membership]:
        res = await self.db.execute(select(Membership).where(Membership.user_id == user_id))
        return list(res.scalars().all())
