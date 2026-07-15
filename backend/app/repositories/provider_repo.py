from app.models.provider import Provider
from app.repositories.base import BaseRepository


class ProviderRepository(BaseRepository[Provider]):
    def __init__(self, db):
        super().__init__(Provider, db)

    async def get_default(self) -> Provider | None:
        from sqlalchemy import select

        res = await self.db.execute(
            select(Provider).where(Provider.is_default.is_(True))
        )
        return res.scalar_one_or_none()

    async def list_all(self) -> list[Provider]:
        return await self.list()
