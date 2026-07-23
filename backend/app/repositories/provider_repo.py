from sqlalchemy import select

from app.models.provider import Provider
from app.repositories.base import BaseRepository


class ProviderRepository(BaseRepository[Provider]):
    def __init__(self, db):
        super().__init__(Provider, db)

    async def get_default(self, org_id: str) -> Provider | None:
        res = await self.db.execute(
            select(Provider).where(Provider.org_id == org_id, Provider.is_default.is_(True))
        )
        return res.scalar_one_or_none()

    async def list_all(self, org_id: str) -> list[Provider]:
        return await self.list(org_id)
