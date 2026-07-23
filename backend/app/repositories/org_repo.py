from __future__ import annotations

from sqlalchemy import select

from app.models.organization import Organization
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    def __init__(self, db):
        super().__init__(Organization, db)

    async def get_by_slug(self, slug: str) -> Organization | None:
        res = await self.db.execute(select(Organization).where(Organization.slug == slug))
        return res.scalar_one_or_none()
